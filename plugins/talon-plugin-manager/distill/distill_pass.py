#!/usr/bin/env python3
"""Build a single consolidated work-packet for a distill pass, so the distill-plugin
skill makes one read call instead of hand-orchestrating list/read/trajectory/repo per
record. Also a `close` command to mark a plugin's processed sessions and compact."""
from __future__ import annotations
import json
import os
import re
import sys

from registry import load_talon_registry
from evidence import EVIDENCE_DIR, read_evidence
from pass_state import ready_plugins, mark_processed, clear_ready, compact_processed
from trajectory import build_trajectory

DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
_GH_RE = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s]+)")


def resolve_repo(install_path: str) -> str | None:
    """Resolve <owner>/<repo> from the plugin's manifest (repository/homepage)."""
    for fname in (".claude-plugin/plugin.json", "plugin.json"):
        try:
            with open(os.path.join(install_path, fname), encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("repository", "homepage"):
            url = cfg.get(key)
            if isinstance(url, str):
                m = _GH_RE.search(url)
                if m:
                    repo = m.group(2)
                    if repo.endswith(".git"):
                        repo = repo[:-4]
                    return f"{m.group(1)}/{repo}"
    return None


def build_packet(store_dir: str, registry: dict[str, str], clip: int = 200) -> dict:
    plugins: list[dict] = []
    for plugin in ready_plugins(store_dir):
        install_path = registry.get(plugin, "")
        records = [r for r in read_evidence(store_dir, plugin) if not r.get("processed", False)]
        sessions = [{
            "session_id": r.get("session_id", ""),
            "kind": r.get("kind", ""),
            "friction": r.get("friction", {}),
            "skills_used": r.get("skills_used", []),
            "transcript_path": r.get("transcript_path", ""),
            "trajectory": build_trajectory(r.get("transcript_path", ""), clip),
        } for r in records]
        plugins.append({
            "plugin": plugin,
            "repo": resolve_repo(install_path) if install_path else None,
            "domain_declared": bool(install_path) and os.path.exists(os.path.join(install_path, "distill.json")),
            "unprocessed": len(records),
            "sessions": sessions,
        })
    return {"store_dir": store_dir, "plugins": plugins}


def main(argv: list[str]) -> int:
    if not argv:
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "packet":
        store = rest[0] if rest else EVIDENCE_DIR
        registry = load_talon_registry(DEFAULT_INSTALLED)
        print(json.dumps(build_packet(store, registry), ensure_ascii=False, indent=2))
    elif cmd == "close":
        store, plugin = rest[0], rest[1]
        sessions = rest[2].split(",") if len(rest) > 2 and rest[2] else []
        mark_processed(store, plugin, sessions)
        compact_processed(store, plugin)
        clear_ready(store, plugin)
        print(f"closed {plugin}: {len(sessions)} session(s)")
    else:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
