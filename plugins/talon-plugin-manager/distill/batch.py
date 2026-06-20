"""Decide when a plugin's accumulated evidence is ready for a (Phase B) distill pass."""
from __future__ import annotations
import os

from evidence import read_evidence


def unprocessed_count(store_dir: str, plugin: str) -> int:
    return sum(1 for r in read_evidence(store_dir, plugin) if not r.get("processed", False))


def should_run_batch(store_dir: str, plugin: str, n_threshold: int = 5) -> bool:
    return unprocessed_count(store_dir, plugin) >= n_threshold


def mark_ready(store_dir: str, plugin: str) -> str:
    os.makedirs(store_dir, exist_ok=True)
    path = os.path.join(store_dir, f"{plugin}.ready")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("ready\n")
    return path
