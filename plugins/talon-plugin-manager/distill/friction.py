"""Deterministic friction pre-scan over a parsed session."""
from __future__ import annotations
import re
from collections import Counter
from dataclasses import asdict, dataclass

from transcript import ToolCall

_CORRECTION = re.compile(
    r"\b(no,|not quite|that'?s wrong|that is wrong|actually|undo|revert|"
    r"that didn'?t work|still (failing|broken|wrong))\b",
    re.IGNORECASE,
)
_ABANDON = re.compile(
    r"\b(never ?mind|forget it|give up|stop,?|let'?s move on|drop it)\b",
    re.IGNORECASE,
)


@dataclass
class FrictionHints:
    has_tool_errors: bool = False
    error_count: int = 0
    repeated_error_count: int = 0
    retry: bool = False
    correction: bool = False
    abandonment: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _error_signature(c: ToolCall) -> str:
    return f"{c.name}:{c.result_text[:60]}"


def scan_friction(calls: list[ToolCall], user_texts: list[str]) -> FrictionHints:
    errors = [c for c in calls if c.is_error]
    sig_counts = Counter(_error_signature(c) for c in errors)
    cmd_counts = Counter(
        str(c.input.get("command", "")) for c in calls if c.name == "Bash" and c.input.get("command")
    )
    joined = "\n".join(user_texts)
    return FrictionHints(
        has_tool_errors=bool(errors),
        error_count=len(errors),
        repeated_error_count=max(sig_counts.values(), default=0),
        retry=any(n >= 2 for n in cmd_counts.values()),
        correction=bool(_CORRECTION.search(joined)),
        abandonment=bool(_ABANDON.search(joined)),
    )
