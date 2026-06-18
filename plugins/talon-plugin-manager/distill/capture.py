#!/usr/bin/env python3
"""SessionEnd capture: append deterministic distillation evidence for any Talon
plugin used (or under-triggered) in the just-ended session. No LLM, no network."""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

from registry import load_talon_registry
from transcript import parse_transcript
from detect import detect_usage, load_domain_map, under_triggered
from friction import scan_friction
from evidence import EVIDENCE_DIR, EvidenceRecord, append_evidence
from batch import should_run_batch, mark_ready

DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")


def run_capture(payload: dict, store_dir: str, installed_plugins_path: str, n_threshold: int = 5) -> list[str]:
    registry = load_talon_registry(installed_plugins_path)
    if not registry:
        return []
    parsed = parse_transcript(payload.get("transcript_path", ""))
    names = set(registry)
    used = detect_usage(parsed.tool_calls, names)
    domain_map = load_domain_map(registry)
    under = under_triggered(parsed.tool_calls, names, domain_map)
    if not used and not under:
        return []
    friction = scan_friction(parsed.tool_calls, parsed.user_texts).as_dict()
    captured_at = datetime.now(timezone.utc).isoformat()
    wrote: list[str] = []
    for plugin in sorted(used | under):
        rec = EvidenceRecord(
            session_id=payload.get("session_id", ""),
            plugin=plugin,
            kind="usage" if plugin in used else "under_trigger",
            skills_used=sorted(used & {plugin}),
            friction=friction,
            captured_at=captured_at,
            transcript_path=payload.get("transcript_path", ""),
        )
        append_evidence(store_dir, rec)
        wrote.append(plugin)
        if should_run_batch(store_dir, plugin, n_threshold):
            mark_ready(store_dir, plugin)
    return wrote


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # never block session end
    try:
        run_capture(payload, EVIDENCE_DIR, DEFAULT_INSTALLED)
    except Exception:
        return 0  # capture is best-effort; never raise into the hook
    return 0


if __name__ == "__main__":
    sys.exit(main())
