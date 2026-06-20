#!/usr/bin/env python3
"""Seed a temp evidence store reproducing the distill-plugin eval scenarios.

Usage: python3 seed_store.py [STORE_DIR]   (default: a fresh temp dir, path printed)

Creates, for plugin 'talon-plugin-manager' (skill onboard-plugin), usage records
with friction and a ready marker; for 'terraform-module-steering', an under_trigger
record. Note the store keys by *plugin* name, not skill name. Point the distill-plugin
skill at the printed store dir to exercise the pipeline without waiting for real
sessions to accumulate.
"""
from __future__ import annotations
import os
import sys
import tempfile

# allow running from the eval dir by importing the plugin's distill package
_DISTILL = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "distill"))
sys.path.insert(0, _DISTILL)

from evidence import EvidenceRecord, append_evidence  # noqa: E402
from batch import mark_ready  # noqa: E402

_FRICTION = {"has_tool_errors": True, "error_count": 2, "repeated_error_count": 2,
             "retry": True, "correction": True, "abandonment": False}


def seed(store_dir: str) -> str:
    for i in range(3):
        append_evidence(store_dir, EvidenceRecord(
            f"onb-{i}", "talon-plugin-manager", "usage", ["talon-plugin-manager:onboard-plugin"],
            _FRICTION, "2026-06-17T00:00:00Z", "/dev/null"))
    append_evidence(store_dir, EvidenceRecord(
        "tms-0", "terraform-module-steering", "under_trigger", [],
        {"has_tool_errors": False}, "2026-06-17T00:00:00Z", "/dev/null"))
    mark_ready(store_dir, "talon-plugin-manager")
    mark_ready(store_dir, "terraform-module-steering")
    return store_dir


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="distill-eval-")
    print(seed(target))
