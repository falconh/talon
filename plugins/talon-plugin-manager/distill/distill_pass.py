#!/usr/bin/env python3
"""Build a single consolidated work-packet for a distill pass, so the distill-plugin
skill makes one read call instead of hand-orchestrating list/read/trajectory/repo per
record. Also a `close` command to mark a plugin's processed sessions and compact."""
from __future__ import annotations
import json
import os
import sys

from registry import load_talon_registry, resolve_repo
from evidence import EVIDENCE_DIR, read_evidence, dedupe_evidence
from pass_state import ready_plugins, mark_processed, clear_ready, compact_processed
from trajectory import build_trajectory

DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")


def resolve_repo_by_skill(skills_used: list[str], registry: dict[str, str]) -> str | None:
    """Reverse-lookup: find the installed plugin that *provides* a used skill
    (`<plugin>:<skill>`) and resolve its repo. Survives plugin renames where the
    evidence's plugin name no longer matches an installed entry."""
    for sid in skills_used:
        skill_name = sid.split(":", 1)[1] if ":" in sid else sid
        if not skill_name:
            continue
        for install_path in registry.values():
            if install_path and os.path.isdir(os.path.join(install_path, "skills", skill_name)):
                repo = resolve_repo(install_path)
                if repo:
                    return repo
    return None


def _packet_repo(install_path: str, records: list[dict], registry: dict[str, str]) -> str | None:
    """3-tier repo resolution: (1) recorded at capture time, (2) registry install
    path by plugin name, (3) reverse-lookup via the skills that fired."""
    for r in records:
        if r.get("repo"):
            return r["repo"]
    repo = resolve_repo(install_path)
    if repo:
        return repo
    skills = [s for r in records for s in (r.get("skills_used") or [])]
    return resolve_repo_by_skill(skills, registry)


def status_rows(store_dir: str, n_threshold: int = 5) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isdir(store_dir):
        return rows
    for fn in sorted(os.listdir(store_dir)):
        if not fn.endswith(".jsonl"):
            continue
        plugin = fn[: -len(".jsonl")]
        recs = dedupe_evidence(read_evidence(store_dir, plugin))
        unprocessed = [r for r in recs if not r.get("processed", False)]
        last = max((r.get("captured_at", "") for r in recs), default="")
        rows.append({
            "plugin": plugin,
            "unprocessed": len(unprocessed),
            "total": len(recs),
            "last_captured": last,
            "ready": len(unprocessed) >= n_threshold,
        })
    return rows


def format_status(store_dir: str, n_threshold: int = 5) -> str:
    rows = status_rows(store_dir, n_threshold)
    if not rows:
        return "no evidence captured yet"
    out = []
    for r in rows:
        verdict = "READY" if r["ready"] else f"waiting ({r['unprocessed']}/{n_threshold})"
        out.append(f"{r['plugin']}: {r['unprocessed']} unprocessed, "
                   f"last {r['last_captured'] or '-'} -> {verdict}")
    return "\n".join(out)


def build_packet(store_dir: str, registry: dict[str, str], clip: int = 200) -> dict:
    plugins: list[dict] = []
    for plugin in ready_plugins(store_dir):
        install_path = registry.get(plugin, "")
        records = [r for r in dedupe_evidence(read_evidence(store_dir, plugin))
                   if not r.get("processed", False)]
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
            "repo": _packet_repo(install_path, records, registry),
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
    elif cmd == "status":
        store = rest[0] if rest else EVIDENCE_DIR
        print(format_status(store))
    else:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
