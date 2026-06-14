#!/usr/bin/env python3
"""Validate a Talon marketplace checkout for dual Claude Code + Codex correctness.

Checks:
  - both catalogs exist and parse
  - every plugin appears in BOTH catalogs (and as the same source kind)
  - local plugins have both manifests, matching versions, and dual-valid skills
    (every SKILL.md frontmatter has `name` AND `description`)
  - remote entries are pinned to a version tag (vX.Y.Z), not a bare branch
  - (warning) local plugin dirs that no catalog references

Usage:  python3 validate_talon.py --root /path/to/talon   # default: .
Exit code 0 = OK (warnings allowed), 1 = errors found.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys

CLAUDE_CATALOG = ".claude-plugin/marketplace.json"
CODEX_CATALOG = ".agents/plugins/marketplace.json"
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+")

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        err(f"missing file: {path}")
    except json.JSONDecodeError as exc:
        err(f"invalid JSON in {path}: {exc}")
    return None


def frontmatter_keys(skill_md: str) -> set[str]:
    """Return the set of top-level YAML keys in a SKILL.md frontmatter block."""
    try:
        with open(skill_md, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        err(f"cannot read {skill_md}: {exc}")
        return set()
    if not text.startswith("---"):
        err(f"{skill_md}: no YAML frontmatter (must start with '---')")
        return set()
    end = text.find("\n---", 3)
    if end == -1:
        err(f"{skill_md}: unterminated frontmatter")
        return set()
    block = text[3:end]
    keys = set()
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):", line)
        if m:
            keys.add(m.group(1))
    return keys


def source_kind(source) -> str:
    """Classify a catalog entry's source as 'local' or 'remote'."""
    if isinstance(source, str):
        return "local"
    if isinstance(source, dict):
        return "local" if source.get("source") == "local" else "remote"
    return "unknown"


def source_ref(source):
    return source.get("ref") if isinstance(source, dict) else None


def check_local_plugin(root: str, name: str) -> None:
    pdir = os.path.join(root, "plugins", name)
    if not os.path.isdir(pdir):
        err(f"[{name}] local plugin dir not found: plugins/{name}")
        return
    claude_m = load_json(os.path.join(pdir, ".claude-plugin/plugin.json"))
    codex_m = load_json(os.path.join(pdir, ".codex-plugin/plugin.json"))
    if claude_m and codex_m:
        cv, xv = claude_m.get("version"), codex_m.get("version")
        if cv != xv:
            err(f"[{name}] manifest version mismatch: claude={cv} codex={xv}")
    skills_dir = os.path.join(pdir, "skills")
    skill_files = []
    if os.path.isdir(skills_dir):
        for entry in sorted(os.listdir(skills_dir)):
            sm = os.path.join(skills_dir, entry, "SKILL.md")
            if os.path.isfile(sm):
                skill_files.append(sm)
    if not skill_files:
        warn(f"[{name}] no skills/<skill>/SKILL.md found")
    for sm in skill_files:
        keys = frontmatter_keys(sm)
        for required in ("name", "description"):
            if required not in keys:
                rel = os.path.relpath(sm, root)
                err(f"[{name}] {rel}: frontmatter missing '{required}'")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="path to the talon repo root")
    args = ap.parse_args()
    root = args.root

    claude = load_json(os.path.join(root, CLAUDE_CATALOG))
    codex = load_json(os.path.join(root, CODEX_CATALOG))
    if claude is None or codex is None:
        return report()

    claude_plugins = {p["name"]: p for p in claude.get("plugins", [])}
    codex_plugins = {p["name"]: p for p in codex.get("plugins", [])}

    # sync check
    only_claude = sorted(set(claude_plugins) - set(codex_plugins))
    only_codex = sorted(set(codex_plugins) - set(claude_plugins))
    for n in only_claude:
        err(f"[{n}] in Claude catalog but not in Codex catalog")
    for n in only_codex:
        err(f"[{n}] in Codex catalog but not in Claude catalog")

    for name in sorted(set(claude_plugins) & set(codex_plugins)):
        c_src = claude_plugins[name].get("source")
        x_src = codex_plugins[name].get("source")
        c_kind, x_kind = source_kind(c_src), source_kind(x_src)
        if c_kind != x_kind:
            err(f"[{name}] source kind differs: claude={c_kind} codex={x_kind}")
            continue
        if c_kind == "local":
            check_local_plugin(root, name)
        elif c_kind == "remote":
            for tool, src in (("claude", c_src), ("codex", x_src)):
                ref = source_ref(src)
                if not ref:
                    err(f"[{name}] remote {tool} source has no 'ref' (pin to a vX.Y.Z tag)")
                elif not TAG_RE.match(str(ref)):
                    warn(f"[{name}] remote {tool} ref '{ref}' is not a vX.Y.Z tag (branch pin?)")
            if "version" not in claude_plugins[name]:
                warn(f"[{name}] Claude remote entry has no 'version' (recommended, match the tag)")
        else:
            err(f"[{name}] unrecognized source: {c_src!r}")

    # orphan local plugin dirs
    plugins_dir = os.path.join(root, "plugins")
    if os.path.isdir(plugins_dir):
        listed = set(claude_plugins) | set(codex_plugins)
        for entry in sorted(os.listdir(plugins_dir)):
            if os.path.isdir(os.path.join(plugins_dir, entry)) and entry not in listed:
                warn(f"[{entry}] plugin dir not referenced by any catalog (orphan?)")

    return report()


def report() -> int:
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s) — FAIL")
        return 1
    print(f"\nOK — 0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
