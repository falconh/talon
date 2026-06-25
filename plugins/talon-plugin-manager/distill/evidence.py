"""Append-only per-plugin evidence store at ~/.claude/talon-distill/evidence/<plugin>.jsonl."""
from __future__ import annotations
import json
import os
from dataclasses import asdict, dataclass

EVIDENCE_DIR = os.path.expanduser("~/.claude/talon-distill/evidence")


@dataclass
class EvidenceRecord:
    session_id: str
    plugin: str
    kind: str  # "usage" | "under_trigger"
    skills_used: list
    friction: dict
    captured_at: str
    transcript_path: str
    processed: bool = False
    repo: str = ""


def _store_path(store_dir: str, plugin: str) -> str:
    return os.path.join(store_dir, f"{plugin}.jsonl")


def append_evidence(store_dir: str, rec: EvidenceRecord) -> str:
    os.makedirs(store_dir, exist_ok=True)
    path = _store_path(store_dir, rec.plugin)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
    return path


def read_evidence(store_dir: str, plugin: str) -> list[dict]:
    path = _store_path(store_dir, plugin)
    rows: list[dict] = []
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return rows
    with fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def dedupe_evidence(rows: list[dict]) -> list[dict]:
    """Collapse to one record per session_id: prefer a processed record, else the newest
    captured_at. Order-preserving by first appearance. Guards against pre-existing
    duplicate captures inflating recurrence counts."""
    best: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        sid = r.get("session_id", "")
        if sid not in best:
            best[sid] = r
            order.append(sid)
            continue
        cur = best[sid]
        if r.get("processed") and not cur.get("processed"):
            best[sid] = r
        elif bool(r.get("processed")) == bool(cur.get("processed")) and \
                str(r.get("captured_at", "")) >= str(cur.get("captured_at", "")):
            best[sid] = r
    return [best[s] for s in order]


def upsert_evidence(store_dir: str, rec: EvidenceRecord) -> str:
    """Idempotent write keyed on session_id: replace an existing unprocessed record for the
    same session; skip if a processed one exists (already judged — never re-judge); else
    append. Rewrites the per-plugin file atomically."""
    os.makedirs(store_dir, exist_ok=True)
    path = _store_path(store_dir, rec.plugin)
    rows = read_evidence(store_dir, rec.plugin)
    kept: list[dict] = []
    for r in rows:
        if r.get("session_id") == rec.session_id:
            if r.get("processed"):
                return path          # already judged; leave the file untouched
            continue                 # drop the stale unprocessed record
        kept.append(r)
    kept.append(asdict(rec))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for d in kept:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return path
