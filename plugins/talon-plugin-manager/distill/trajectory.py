#!/usr/bin/env python3
"""Deterministic, clipped render of a session transcript for distillation reflection."""
from __future__ import annotations
import sys

from transcript import parse_transcript

_ARG_FIELD = {"Bash": "command", "Skill": "skill", "Edit": "file_path",
              "Write": "file_path", "Read": "file_path", "NotebookEdit": "notebook_path"}


def build_trajectory(transcript_path: str, clip: int = 200) -> str:
    parsed = parse_transcript(transcript_path)
    lines: list[str] = []
    for i, c in enumerate(parsed.tool_calls, 1):
        status = "✗" if c.is_error else "✓"
        arg = str(c.input.get(_ARG_FIELD.get(c.name, ""), "")).strip()
        head = f"{i}. [{status}] {c.name}" + (f" {arg}" if arg else "")
        res = (c.result_text or "").replace("\n", " ").strip()[:clip]
        lines.append(head + (f" → {res}" if res else ""))
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_trajectory(sys.argv[1]) if len(sys.argv) > 1 else "")
