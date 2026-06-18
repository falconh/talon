#!/usr/bin/env python3
"""Emit gate: scrub a finding, quarantine if dirty, else open/update/reopen its issue."""
from __future__ import annotations
import argparse
import json
import sys

import issues
from fingerprint import finding_fingerprint, marker
from quarantine import QUARANTINE_DIR, quarantine
from redact import scan_secrets


def emit_finding(finding: dict, runner=issues.default_runner, quarantine_dir: str = QUARANTINE_DIR) -> dict:
    repo = finding["repo"]
    fp = finding_fingerprint(finding["plugin"], finding["decision"], finding["anchor"])
    body = finding["body"].rstrip() + "\n\n" + marker(fp)
    hits = scan_secrets(finding.get("title", "") + "\n" + body)
    if hits:
        path = quarantine(
            {**finding, "fingerprint": fp, "secret_kinds": sorted({k for k, _ in hits})},
            "secret-scan-blocked", quarantine_dir,
        )
        return {"status": "quarantined", "fingerprint": fp, "path": path}

    existing = issues.find_existing(repo, fp, runner)
    labels = finding.get("labels", ["distillation"])
    note = finding.get("recurrence_note", f"Recurred (fingerprint `{fp}`).")
    if existing is None:
        url = issues.open_issue(repo, finding["title"], body, labels, runner)
        return {"status": "opened", "fingerprint": fp, "url": url}
    number = existing["number"]
    if str(existing.get("state", "")).upper() == "CLOSED":
        issues.reopen(repo, number, runner)
        issues.comment(repo, number, "Reopened as regression. " + note, runner)
        return {"status": "reopened", "fingerprint": fp, "number": number}
    issues.comment(repo, number, note, runner)
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
