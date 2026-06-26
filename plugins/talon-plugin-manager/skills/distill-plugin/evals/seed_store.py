#!/usr/bin/env python3
"""Seed a temp evidence store reproducing the distill-plugin eval scenarios.

Usage: python3 seed_store.py [STORE_DIR]   (default: a fresh temp dir, path printed)

Creates, for plugin 'talon-plugin-manager' (skill onboard-plugin), usage records with
friction; for 'terraform-module-steering', under_trigger records. Each plugin gets
THRESHOLD records and a ready marker, so the count-based preflight (`distill_pass.py
status`) reports READY in agreement with the marker the work-packet reads — otherwise a
faithful agent told by the preflight "there may be nothing to process yet" could stop
before ever filing an issue. Note the store keys by *plugin* name, not skill name. Point
the distill-plugin skill at the printed store dir (or export TALON_DISTILL_HOME and let
its default resolve there) to exercise the pipeline without waiting for real sessions.
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

THRESHOLD = 5  # mark_ready fires at this count in real capture (batch.should_run_batch)
_FRICTION = {"has_tool_errors": True, "error_count": 2, "repeated_error_count": 2,
             "retry": True, "correction": True, "abandonment": False}


def seed(store_dir: str) -> str:
    for i in range(THRESHOLD):
        append_evidence(store_dir, EvidenceRecord(
            f"onb-{i}", "talon-plugin-manager", "usage", ["talon-plugin-manager:onboard-plugin"],
            _FRICTION, "2026-06-17T00:00:00Z", "/dev/null"))
        append_evidence(store_dir, EvidenceRecord(
            f"tms-{i}", "terraform-module-steering", "under_trigger", [],
            {"has_tool_errors": False}, "2026-06-17T00:00:00Z", "/dev/null"))
    mark_ready(store_dir, "talon-plugin-manager")
    mark_ready(store_dir, "terraform-module-steering")
    return store_dir


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="distill-eval-")
    print(seed(target))
