"""Thin gh-CLI wrapper for distillation issues. All calls go through an injectable runner."""
from __future__ import annotations
import json
import subprocess


def default_runner(args: list[str]) -> tuple[int, str, str]:
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
