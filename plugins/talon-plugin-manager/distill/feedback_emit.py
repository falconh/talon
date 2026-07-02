#!/usr/bin/env python3
"""Feedback emit: scrub a skill-feedback finding, quarantine if dirty, else open its issue.
No dedup — a human approves every file, so there is no fingerprint or existing-issue lookup."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import issues
from paths import under
from quarantine import QUARANTINE_DIR, quarantine
from redact import scan_secrets

DENYLIST_FILE = under("denylist.txt")
PENDING_DIR = under("pending")


def _load_denylist() -> list[str]:
    try:
        with open(DENYLIST_FILE, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return []


def _finding_id(finding: dict) -> str:
    """Stable local id for the pending filename (no dedup semantics)."""
    key = f"{finding.get('plugin', '')}|{finding.get('skill', '')}|{finding.get('title', '')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _defer(finding: dict, fid: str, body: str, pending_dir: str) -> str:
    os.makedirs(pending_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = os.path.join(pending_dir, f"{ts}-{fid}.md")
    labels = ",".join(finding.get("labels", ["distill-feedback"]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {finding.get('title', '')}\n\nrepo: {finding['repo']}\nlabels: {labels}\n\n{body}\n")
    return path


def file_feedback(finding: dict, runner=issues.default_runner, quarantine_dir: str = QUARANTINE_DIR,
                  denylist: list[str] | None = None, backend: str | None = None,
                  pending_dir: str = PENDING_DIR) -> dict:
    if denylist is None:
        denylist = _load_denylist()
    body = finding["body"].rstrip() + "\n"
    hits = scan_secrets(finding.get("title", "") + "\n" + body, denylist)
    if hits:
        path = quarantine({**finding, "secret_kinds": sorted({k for k, _ in hits})},
                          "secret-scan-blocked", quarantine_dir)
        return {"status": "quarantined", "path": path}
    backend = backend or issues.select_backend()
    if backend == "none":
        return {"status": "deferred", "path": _defer(finding, _finding_id(finding), body, pending_dir)}
    labels = finding.get("labels", ["distill-feedback"])
    url = issues.open_issue(finding["repo"], finding["title"], body, labels, runner, backend=backend)
    return {"status": "opened", "url": url}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--finding-file", required=True)
    args = ap.parse_args()
    with open(args.finding_file, encoding="utf-8") as fh:
        finding = json.load(fh)
    print(json.dumps(file_feedback(finding)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
