"""GitHub issue transport for distillation. Supports two backends callable from Python —
the `gh` CLI and the raw REST API (stdlib urllib, no `gh`/`curl` binary required) — and
auto-selects: gh if installed, else the API if a token is present. (A third transport, the
GitHub MCP server, is agent-level and driven from the SKILL.md, not here.) All gh calls go
through an injectable runner; all API calls through an injectable http callable."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


# ---- backend selection -------------------------------------------------------

def gh_available() -> bool:
    return shutil.which("gh") is not None


def github_token() -> str:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def select_backend(have_gh: bool | None = None, token: str | None = None) -> str:
    """Return the transport to use: 'dry' | 'gh' | 'api' | 'none'."""
    if os.environ.get("TALON_DISTILL_DRY_RUN"):
        return "dry"
    have_gh = gh_available() if have_gh is None else have_gh
    token = github_token() if token is None else token
    if have_gh:
        return "gh"
    if token:
        return "api"
    return "none"


# ---- gh transport (subprocess; dry-run aware) --------------------------------

def _dry_runner(args: list[str]) -> tuple[int, str, str]:
    """Record the gh command and return canned output — never touches the network."""
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


# ---- api transport (stdlib urllib) -------------------------------------------

def api_request(method: str, path: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    """One GitHub REST call. Returns (status, json|{}). Never raises."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "talon-distill")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            txt = resp.read().decode("utf-8")
            return resp.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return 0, {}


# ---- operations (dispatch on backend) ----------------------------------------

def find_existing(repo: str, fp: str, runner=default_runner, backend: str | None = None, http=None) -> dict | None:
    backend = backend or select_backend()
    http = http or api_request
    if backend == "api":
        q = urllib.parse.quote(f"repo:{repo} {fp} in:body type:issue")
        status, data = http("GET", f"/search/issues?q={q}", github_token())
        if status != 200:
            return None
        for it in data.get("items", []):
            if fp in (it.get("body") or ""):
                return {"number": it.get("number"), "state": str(it.get("state", "")).upper(),
                        "body": it.get("body"), "title": it.get("title")}
        return None
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


def open_issue(repo: str, title: str, body: str, labels: list[str], runner=default_runner,
               backend: str | None = None, http=None) -> str:
    backend = backend or select_backend()
    http = http or api_request
    if backend == "api":
        status, data = http("POST", f"/repos/{repo}/issues", github_token(),
                            {"title": title, "body": body, "labels": labels})
        return data.get("html_url", "") if status in (200, 201) else ""
    args = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body]
    for label in labels:
        args += ["--label", label]
    code, out, _ = runner(args)
    return out.strip() if code == 0 else ""


def comment(repo: str, number: int, note: str, runner=default_runner,
            backend: str | None = None, http=None) -> None:
    backend = backend or select_backend()
    http = http or api_request
    if backend == "api":
        http("POST", f"/repos/{repo}/issues/{number}/comments", github_token(), {"body": note})
        return
    runner(["gh", "issue", "comment", str(number), "--repo", repo, "--body", note])


def reopen(repo: str, number: int, runner=default_runner,
           backend: str | None = None, http=None) -> None:
    backend = backend or select_backend()
    http = http or api_request
    if backend == "api":
        http("PATCH", f"/repos/{repo}/issues/{number}", github_token(), {"state": "open"})
        return
    runner(["gh", "issue", "reopen", str(number), "--repo", repo])
