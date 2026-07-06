"""Quarantine flagged distillation findings for manual review — redaction Layer 3."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

from paths import under

QUARANTINE_DIR = under("_quarantine")


def quarantine(finding: dict, reason: str, quarantine_dir: str = QUARANTINE_DIR) -> str:
    os.makedirs(quarantine_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    plugin = str(finding.get("plugin", "unknown"))
    path = os.path.join(quarantine_dir, f"{ts}-{plugin}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"reason": reason, "finding": finding}, fh, ensure_ascii=False, indent=2)
    return path
