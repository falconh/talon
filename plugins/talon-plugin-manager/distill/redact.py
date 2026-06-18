"""Deterministic secret/PII scrubber — redaction Layer 2 (hard pre-post blocker)."""
from __future__ import annotations
import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b")),
    ("slack_token", re.compile(r"\bxox[bpars]-[0-9A-Za-z-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[0-9A-Za-z_-]{6,}\.eyJ[0-9A-Za-z_-]{6,}\.[0-9A-Za-z_-]{6,}\b")),
    ("aws_account_id", re.compile(r"\b\d{12}\b")),
    ("arn", re.compile(r"\barn:aws[0-9a-z-]*:[0-9a-z-]*:")),
    ("private_ip", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]


def scan_secrets(text: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text or ""):
            hits.append((kind, m.group(0)))
    return hits


def is_clean(text: str) -> bool:
    return not scan_secrets(text)
