#!/usr/bin/env python3
"""SessionEnd capture: append deterministic distillation evidence for any Talon
plugin used (or under-triggered) in the just-ended session. No LLM, no network."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from registry import load_talon_registry, resolve_repo
from transcript import parse_transcript
from detect import detect_usage, load_domain_map, under_triggered
from friction import scan_friction
from evidence import EVIDENCE_DIR, EvidenceRecord, append_evidence
from batch import should_run_batch, mark_ready

DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")


def _default_spawner(plugin: str) -> None:
    """Best-effort detached `claude -p` distill pass for one plugin. Never raises."""
    env = dict(os.environ)
    env["TALON_DISTILL_CHILD"] = "1"
    prompt = (
        f"Use the talon-plugin-manager distill-plugin skill to process the distillation "
        f"evidence queue for plugin '{plugin}'. Process only the ready queue, then exit."
    )
    try:
        subprocess.Popen(
            ["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except (OSError, ValueError):
        pass


def run_capture(payload: dict, store_dir: str, installed_plugins_path: str,
                n_threshold: int = 5, spawner=None) -> list[str]:
    if os.environ.get("TALON_DISTILL_CHILD") == "1":
        return []  # never capture inside an auto-spawned distill session (no recursion)
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
        skills_used = sorted(s for c in parsed.tool_calls if c.name == "Skill"
                             for s in [str(c.input.get("skill", ""))]
                             if s.split(":", 1)[0] == plugin)
        rec = EvidenceRecord(
            session_id=payload.get("session_id", ""),
            plugin=plugin,
            kind="usage" if plugin in used else "under_trigger",
            skills_used=skills_used,
            friction=friction,
            captured_at=captured_at,
            transcript_path=payload.get("transcript_path", ""),
            repo=resolve_repo(registry.get(plugin, "")) or "",
        )
        append_evidence(store_dir, rec)
        wrote.append(plugin)
        if should_run_batch(store_dir, plugin, n_threshold):
            mark_ready(store_dir, plugin)
            if spawner is not None:
                spawner(plugin)
    return wrote


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # never block session end
    try:
        run_capture(payload, EVIDENCE_DIR, DEFAULT_INSTALLED, spawner=_default_spawner)
    except Exception:
        return 0  # capture is best-effort; never raise into the hook
    return 0


if __name__ == "__main__":
    sys.exit(main())
