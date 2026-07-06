#!/usr/bin/env python3
"""Resolve the target marketplace (repo slug + default branch) for onboard-plugin.

onboard-plugin must work with ANY GitHub-hosted dual Claude Code + Codex marketplace,
so it never hardcodes one. This helper computes the *default* marketplace to offer the
user — normally the marketplace this very skill was installed from (its "root
marketplace") — and resolves that repo's live default branch, so the skill can present
a correct default and let the user confirm or override it.

Repo-slug resolution (first hit wins):
  1. --repo owner/name   explicit override (what the user confirmed or typed)
  2. config file         --config PATH, else <skill-dir>/marketplace.config.json if present
  3. self-location       this script's own install path -> marketplace name
                         -> ~/.claude/plugins/known_marketplaces.json -> repo slug
  4. checkout git remote `git -C <--root> remote get-url origin`, ONLY if that dir looks
                         like a marketplace checkout (has .claude-plugin/marketplace.json).
                         Pass --root <marketplace-checkout> to target a specific one.

Default branch: config's `defaultBranch` if set, else a live
`git ls-remote --symref https://github.com/<slug>.git HEAD` (plain git, no gh, no SSH).

Prints a JSON object to stdout and never raises. When nothing resolves it prints
{"resolved": false, ...} so the skill knows to ASK the user for the marketplace.

Usage:
  python3 resolve_marketplace.py                 # self-detect the root marketplace
  python3 resolve_marketplace.py --repo o/r       # resolve a specific marketplace
  python3 resolve_marketplace.py --config c.json  # read identity from a config file
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys

KNOWN_MARKETPLACES = os.path.expanduser("~/.claude/plugins/known_marketplaces.json")
CLAUDE_CATALOG = ".claude-plugin/marketplace.json"
SLUG_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


def _slug_from_url(url: str) -> str | None:
    """Extract owner/repo from an https or ssh GitHub remote URL."""
    url = url.strip()
    for pfx in ("git@github.com:", "https://github.com/", "ssh://git@github.com/"):
        if url.startswith(pfx):
            slug = url[len(pfx):]
            if slug.endswith(".git"):
                slug = slug[:-4]
            return slug if SLUG_RE.match(slug) else None
    return None


def _git(args: list[str], cwd: str | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def marketplace_from_self_location(script_file: str):
    """(name, slug) parsed from THIS script's own install path, or (None, None).

    Installed skills live under either
      ~/.claude/plugins/marketplaces/<name>/plugins/<plugin>/skills/<skill>/...   or
      ~/.claude/plugins/cache/<name>/<plugin>/<version>/skills/<skill>/...
    so the marketplace name is the path segment right after plugins/{marketplaces,cache}.
    """
    parts = os.path.abspath(script_file).split(os.sep)
    name = None
    for i, seg in enumerate(parts[:-1]):
        if seg in ("marketplaces", "cache") and i > 0 and parts[i - 1] == "plugins":
            name = parts[i + 1]
            break
    if not name:
        return None, None
    slug = None
    try:
        with open(KNOWN_MARKETPLACES, encoding="utf-8") as fh:
            data = json.load(fh)
        slug = data.get(name, {}).get("source", {}).get("repo")
    except (OSError, ValueError):
        pass
    return name, slug


def load_config(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def resolve_default_branch(slug: str) -> str | None:
    """Live default branch via git ls-remote over HTTPS (no gh, no SSH key needed)."""
    out = _git(["ls-remote", "--symref", f"https://github.com/{slug}.git", "HEAD"])
    if not out:
        return None
    for line in out.splitlines():
        m = re.match(r"ref:\s+refs/heads/(\S+)\s+HEAD", line)
        if m:
            return m.group(1)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve the target marketplace repo + default branch.")
    ap.add_argument("--repo", help="explicit owner/name override")
    ap.add_argument("--config", help="path to a marketplace.config.json")
    ap.add_argument("--root", default=".", help="marketplace checkout to detect from (its origin remote); default: cwd")
    ap.add_argument("--skill-dir", help="skill dir to look for marketplace.config.json (default: derived)")
    args = ap.parse_args()

    skill_dir = args.skill_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = {"resolved": False, "repo": None, "name": None,
              "defaultBranch": None, "source": None, "hint": None}

    # 1. explicit override
    if args.repo:
        if not SLUG_RE.match(args.repo):
            result["hint"] = f"--repo {args.repo!r} is not owner/name"
            print(json.dumps(result)); return 1
        result.update(repo=args.repo, source="override")

    # 2. config file (explicit, or bundled next to the skill)
    cfg = None
    if not result["repo"]:
        cfg_path = args.config or os.path.join(skill_dir, "marketplace.config.json")
        cfg = load_config(cfg_path) if os.path.isfile(cfg_path) else None
        if cfg and cfg.get("repo") and SLUG_RE.match(str(cfg["repo"])):
            result.update(repo=cfg["repo"], name=cfg.get("name"), source="config")

    # 3. self-location (the skill's own root marketplace)
    if not result["repo"]:
        name, slug = marketplace_from_self_location(__file__)
        if slug:
            result.update(repo=slug, name=name, source="self-location")
        elif name:
            result.update(name=name, hint=f"marketplace {name!r} not in known_marketplaces.json "
                                          "(Codex, or added under another name) — confirm the repo")

    # 4. git remote of --root, only if that dir is itself a marketplace checkout.
    #    Use --root to point at the TARGET marketplace's checkout so this detects its
    #    origin, not whatever repo the session happens to be running in.
    if not result["repo"] and os.path.isfile(os.path.join(args.root, CLAUDE_CATALOG)):
        url = _git(["remote", "get-url", "origin"], cwd=args.root)
        slug = _slug_from_url(url) if url else None
        if slug:
            result.update(repo=slug, source="checkout-git")

    if not result["repo"]:
        result["hint"] = result["hint"] or ("could not auto-detect a marketplace — "
                                             "ask the user for its owner/name")
        print(json.dumps(result)); return 0

    # default branch: config pin, else live lookup
    if cfg and cfg.get("defaultBranch"):
        result["defaultBranch"] = cfg["defaultBranch"]
    else:
        result["defaultBranch"] = resolve_default_branch(result["repo"])
    result["resolved"] = True
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
