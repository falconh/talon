#!/usr/bin/env python3
"""Emit gate: scrub a finding, quarantine if dirty, else open/update/reopen its issue."""
from __future__ import annotations
import argparse
import json
import os
import sys

import issues
from fingerprint import finding_fingerprint, marker
from paths import under
from quarantine import QUARANTINE_DIR, quarantine
from redact import scan_secrets

DENYLIST_FILE = under("denylist.txt")
PENDING_DIR = under("pending")


def _defer(finding: dict, fp: str, body: str, pending_dir: str = PENDING_DIR) -> str:
    """No GitHub transport (no gh, no token, not dry-run). Write the already-redacted issue
    to pending/ so it can be posted by hand (or by the agent via the GitHub MCP server)."""
    os.makedirs(pending_dir, exist_ok=True)
    path = os.path.join(pending_dir, f"{fp}.md")
    labels = ",".join(finding.get("labels", ["distillation"]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {finding.get('title', '')}\n\nrepo: {finding['repo']}\nlabels: {labels}\n\n{body}\n")
    return path


def _load_denylist() -> list[str]:
    """Optional proprietary terms (org names, internal hostnames) to block, one per
    line; blanks and #-comments ignored. Absent file => empty denylist."""
    try:
        with open(DENYLIST_FILE, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return []


def emit_finding(finding: dict, runner=issues.default_runner, quarantine_dir: str = QUARANTINE_DIR,
                 denylist: list[str] | None = None, backend: str | None = None,
                 pending_dir: str = PENDING_DIR) -> dict:
    if denylist is None:
        denylist = _load_denylist()
    repo = finding["repo"]
    fp = finding_fingerprint(finding["plugin"], finding["decision"], finding["anchor"])
    body = finding["body"].rstrip() + "\n\n" + marker(fp)
    hits = scan_secrets(finding.get("title", "") + "\n" + body, denylist)
    if hits:
        path = quarantine(
            {**finding, "fingerprint": fp, "secret_kinds": sorted({k for k, _ in hits})},
            "secret-scan-blocked", quarantine_dir,
        )
        return {"status": "quarantined", "fingerprint": fp, "path": path}

    backend = backend or issues.select_backend()
    if backend == "none":  # no gh, no token, not dry-run — preserve the (redacted) finding
        return {"status": "deferred", "fingerprint": fp, "path": _defer(finding, fp, body, pending_dir)}

    existing = issues.find_existing(repo, fp, runner, backend=backend)
    labels = finding.get("labels", ["distillation"])
    note = finding.get("recurrence_note", f"Recurred (fingerprint `{fp}`).")
    if existing is None:
        url = issues.open_issue(repo, finding["title"], body, labels, runner, backend=backend)
        return {"status": "opened", "fingerprint": fp, "url": url}
    number = existing["number"]
    if str(existing.get("state", "")).upper() == "CLOSED":
        issues.reopen(repo, number, runner, backend=backend)
        issues.comment(repo, number, "Reopened as regression. " + note, runner, backend=backend)
        return {"status": "reopened", "fingerprint": fp, "number": number}
    issues.comment(repo, number, note, runner, backend=backend)
    return {"status": "updated", "fingerprint": fp, "number": number}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--finding-file", required=True)
    args = ap.parse_args()
    with open(args.finding_file, encoding="utf-8") as fh:
        finding = json.load(fh)
    print(json.dumps(emit_finding(finding)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
