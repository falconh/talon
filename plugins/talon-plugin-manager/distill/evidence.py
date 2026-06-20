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
