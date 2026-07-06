#!/usr/bin/env python3
"""PostToolUse re-assert: when a Talon-registry plugin's skill is invoked, remind the agent to
watch for USER dissatisfaction. Silent for non-Talon skills, skill-feedback itself, and non-Skill
tools. Reads the hook payload on stdin, prints hook JSON on stdout. Never raises into the hook."""
from __future__ import annotations
import json
import sys

from paths import installed_plugins
from registry import load_talon_registry

REASSERT = ("[talon-skill-feedback] You just used {skill}. Watch the user's next reactions: if they "
            "correct it, redo the work themselves, show frustration, or abandon the approach, invoke "
            "the plugin-manager skill-feedback skill. Judge the user's reaction, not your own "
            "output.")


def reassert_for(payload: dict, registry: dict) -> str | None:
    if payload.get("tool_name") != "Skill":
        return None
    skill = str((payload.get("tool_input") or {}).get("skill", ""))
    plugin = skill.split(":", 1)[0]
    if not plugin or plugin not in registry:
        return None
    if skill.endswith(":skill-feedback"):
        return None  # recursion guard: never monitor the feedback flow itself
    return REASSERT.format(skill=skill)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    try:
        registry = load_talon_registry(installed_plugins())
        note = reassert_for(payload, registry)
    except Exception:
        return 0
    if note:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
