#!/usr/bin/env python3
"""Track which evidence has been distilled and which plugins are queued for a pass."""
from __future__ import annotations
import json
import os
import sys


def ready_plugins(store_dir: str) -> list[str]:
    try:
        names = os.listdir(store_dir)
    except OSError:
        return []
    return sorted(n[:-len(".ready")] for n in names if n.endswith(".ready"))


def clear_ready(store_dir: str, plugin: str) -> None:
    try:
        os.remove(os.path.join(store_dir, f"{plugin}.ready"))
    except OSError:
        pass


def mark_processed(store_dir: str, plugin: str, session_ids: list[str]) -> int:
    path = os.path.join(store_dir, f"{plugin}.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        return 0
    sids = set(session_ids)
    changed = 0
    out: list[str] = []
    for ln in raw:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            out.append(ln)
            continue
        if r.get("session_id") in sids and not r.get("processed", False):
            r["processed"] = True
            changed += 1
        out.append(json.dumps(r, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + ("\n" if out else ""))
    return changed


def compact_processed(store_dir: str, plugin: str) -> int:
    """Drop already-processed records, keeping only unprocessed ones. Returns the
    number dropped. Keeps the append-only store from growing without bound."""
    path = os.path.join(store_dir, f"{plugin}.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        return 0
    kept: list[str] = []
    dropped = 0
    for ln in raw:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            kept.append(ln)
            continue
        if r.get("processed", False):
            dropped += 1
        else:
            kept.append(json.dumps(r, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(kept) + ("\n" if kept else ""))
    return dropped


def main(argv: list[str]) -> int:
    if not argv:
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "list-ready":
        print("\n".join(ready_plugins(rest[0])))
    elif cmd == "mark-processed":
        print(mark_processed(rest[0], rest[1], rest[2].split(",") if len(rest) > 2 and rest[2] else []))
    elif cmd == "clear-ready":
        clear_ready(rest[0], rest[1])
    elif cmd == "compact":
        print(compact_processed(rest[0], rest[1]))
    else:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
