"""Single source of truth for where distill writes on disk.

Everything distill persists — the evidence store, ready markers, pending/quarantine
findings, the inferred domain map, the denylist, and the dry-run/runtime logs — lives
under one root. `TALON_DISTILL_HOME` overrides the default (~/.claude/talon-distill) so
evals and the headless auto-pass can run against a throwaway tree instead of the user's
real evidence store.

Constants in the other modules are resolved at import time via `under(...)`, so a
subprocess that exports the env var before `python3 <tool>.py` picks up the override.
In-process callers that need a different root keep passing explicit dirs (as the tests
already do); they never depend on this env var.
"""
from __future__ import annotations
import os

DEFAULT_HOME = "~/.claude/talon-distill"


def home() -> str:
    """The distill root, honoring TALON_DISTILL_HOME (empty/unset => the default)."""
    return os.path.expanduser(os.environ.get("TALON_DISTILL_HOME") or DEFAULT_HOME)


def under(*parts: str) -> str:
    """A path under the distill root."""
    return os.path.join(home(), *parts)
