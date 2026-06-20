"""Thin gh-CLI wrapper for distillation issues. All calls go through an injectable runner."""
from __future__ import annotations
import json
import os
import subprocess


def _dry_runner(args: list[str]) -> tuple[int, str, str]:
    """Record the gh command and return canned output — never touches the network.
    Enabled by TALON_DISTILL_DRY_RUN; log path from TALON_DISTILL_DRY_LOG."""
    log = os.environ.get("TALON_DISTILL_DRY_LOG", os.path.expanduser("~/.claude/talon-distill/dry_run.log"))
    try:
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(" ".join(args) + "\n")
    except OSError:
        pass
    if args[:3] == ["gh", "issue", "list"]:
        return 0, "[]", ""
    if args[:3] == ["gh", "issue", "create"]:
        return 0, "https://github.com/DRY-RUN/repo/issues/0\n", ""
    return 0, "", ""


def default_runner(args: list[str]) -> tuple[int, str, str]:
    if os.environ.get("TALON_DISTILL_DRY_RUN"):
        return _dry_runner(args)
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def find_existing(repo: str, fp: str, runner=default_runner) -> dict | None:
    code, out, _ = runner([
        "gh", "issue", "list", "--repo", repo, "--state", "all",
        "--search", fp, "--json", "number,state,body,title", "--limit", "50",
    ])
    if code != 0:
        return None
    try:
        items = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    for it in items:
        if fp in (it.get("body") or ""):
            return it
    return None


def open_issue(repo: str, title: str, body: str, labels: list[str], runner=default_runner) -> str:
    args = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body]
    for label in labels:
        args += ["--label", label]
    code, out, _ = runner(args)
    return out.strip() if code == 0 else ""


def comment(repo: str, number: int, note: str, runner=default_runner) -> None:
    runner(["gh", "issue", "comment", str(number), "--repo", repo, "--body", note])


def reopen(repo: str, number: int, runner=default_runner) -> None:
    runner(["gh", "issue", "reopen", str(number), "--repo", repo])
