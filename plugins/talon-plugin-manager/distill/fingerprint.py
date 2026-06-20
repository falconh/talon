"""Stable fingerprint for a distillation finding, embedded as a hidden issue marker."""
from __future__ import annotations
import hashlib
import re

_MARKER_RE = re.compile(r"<!-- distill-fp: ([0-9a-f]{12}) -->")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def finding_fingerprint(plugin: str, decision: str, anchor: str) -> str:
    raw = f"{plugin}|{decision}|{_norm(anchor)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def marker(fp: str) -> str:
    return f"<!-- distill-fp: {fp} -->"


def extract_fp(body: str) -> str | None:
    m = _MARKER_RE.search(body or "")
    return m.group(1) if m else None
