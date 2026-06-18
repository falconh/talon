"""Detect which Talon plugins were used (Skill calls) or under-triggered (domain
activity with no skill fired) in a parsed session."""
from __future__ import annotations
import json
import os
import re

from transcript import ToolCall

_PATH_TOOLS = {"Edit", "Write", "Read", "NotebookEdit"}


def _glob_to_regex(glob: str) -> str:
    """Path-aware glob → regex. `**` spans directories, `*` stays within a
    segment, `?` is one non-slash char. Version-independent (no PurePath.full_match,
    which is 3.13-only) so under-trigger detection works on any python3."""
    glob = glob.replace("\\", "/")
    out: list[str] = []
    i, n = 0, len(glob)
    while i < n:
        if glob[i:i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif glob[i:i + 2] == "**":
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return "^" + "".join(out) + "$"


def _glob_match(path: str, glob: str) -> bool:
    return re.match(_glob_to_regex(glob), str(path).replace("\\", "/")) is not None


def detect_usage(calls: list[ToolCall], registry_names: set[str]) -> set[str]:
    used: set[str] = set()
    for c in calls:
        if c.name != "Skill":
            continue
        skill = str(c.input.get("skill", ""))
        plugin = skill.split(":", 1)[0]
        if plugin in registry_names:
            used.add(plugin)
    return used


def load_domain_map(registry: dict[str, str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for plugin, install_path in registry.items():
        if not install_path:
            continue
        cfg_path = os.path.join(install_path, "distill.json")
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        out[plugin] = {
            "globs": list(cfg.get("domain_globs") or []),
            "cmds": list(cfg.get("domain_cmds") or []),
        }
    return out


def _file_paths(calls: list[ToolCall]) -> list[str]:
    paths = []
    for c in calls:
        if c.name in _PATH_TOOLS:
            p = c.input.get("file_path") or c.input.get("notebook_path")
            if p:
                paths.append(str(p))
    return paths


def _commands(calls: list[ToolCall]) -> list[str]:
    return [str(c.input.get("command", "")) for c in calls if c.name == "Bash"]


def detect_domain(calls: list[ToolCall], domain_map: dict[str, dict]) -> set[str]:
    paths = _file_paths(calls)
    commands = _commands(calls)
    active: set[str] = set()
    for plugin, sig in domain_map.items():
        cmd_hit = any(
            re.search(rf"\b{re.escape(cmd)}\b", command)
            for cmd in sig.get("cmds", [])
            for command in commands
        )
        glob_hit = any(
            _glob_match(path, glob)
            for glob in sig.get("globs", [])
            for path in paths
        )
        if cmd_hit or glob_hit:
            active.add(plugin)
    return active


def under_triggered(calls: list[ToolCall], registry_names: set[str], domain_map: dict[str, dict]) -> set[str]:
    return detect_domain(calls, domain_map) - detect_usage(calls, registry_names)
