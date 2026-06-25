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
from windows import per_plugin_friction
from evidence import EVIDENCE_DIR, EvidenceRecord, upsert_evidence
from batch import should_run_batch, mark_ready

DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")


# Tools the headless auto-pass needs. gh is reached transitively via `python3 emit.py`
# (a subprocess of python, not a gated tool call), so we never allow `Bash(gh:*)` globally —
# allowing python3 inside this bounded child session is enough to run the whole pipeline.
AUTO_ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Write", "Bash(python3:*)", "Bash(mkdir:*)", "Bash(cat:*)"]
PENDING_DIR = os.path.expanduser("~/.claude/talon-distill/pending")


def _spawn_env(plugin: str) -> dict:
    """Environment for the auto-spawned pass. Safe by default: the pass drafts + redacts
    and LOGS what it would file (dry-run) rather than auto-posting to a public repo. Set
    TALON_DISTILL_AUTOPOST=1 to actually post automatically."""
    env = dict(os.environ)
    env["TALON_DISTILL_CHILD"] = "1"  # recursion guard: child sessions don't re-capture
    if env.get("TALON_DISTILL_AUTOPOST") == "1":
        env.pop("TALON_DISTILL_DRY_RUN", None)  # opt-in: real posting
    else:
        env["TALON_DISTILL_DRY_RUN"] = "1"
        env["TALON_DISTILL_DRY_LOG"] = os.path.join(PENDING_DIR, f"{plugin}.log")
    return env


def _spawn_command(plugin: str) -> list[str]:
    prompt = (
        f"Use the talon-plugin-manager distill-plugin skill to process the distillation "
        f"evidence queue for plugin '{plugin}'. Process only the ready queue, then exit."
    )
    return ["claude", "-p", prompt, "--permission-mode", "acceptEdits",
            "--allowedTools", *AUTO_ALLOWED_TOOLS]


def _default_spawner(plugin: str) -> None:
    """Best-effort detached `claude -p` distill pass for one plugin. Never raises."""
    try:
        subprocess.Popen(
            _spawn_command(plugin), env=_spawn_env(plugin),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
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
    friction_map = per_plugin_friction(parsed, used, under, domain_map)
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
            friction=friction_map[plugin],
            captured_at=captured_at,
            transcript_path=payload.get("transcript_path", ""),
            repo=resolve_repo(registry.get(plugin, "")) or "",
        )
        upsert_evidence(store_dir, rec)
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
