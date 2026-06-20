# GitHub access — backends & order (shared)

Not every workstation has the `gh` CLI. Both skills reach GitHub through one of three
transports, tried in this order:

1. **`gh` CLI** — used if `gh` is on `PATH` (and authenticated). Simplest; no token handling.
2. **GitHub MCP server** — if the session exposes GitHub MCP tools (e.g. `mcp__github__*` /
   `create_issue` / `create_pull_request`). These are **agent-level** tools (only the model can
   call them — a Python script cannot), so they're driven from the skill, not the helper code.
3. **REST API (last resort)** — a direct HTTPS call to `https://api.github.com`, using a token
   from `GH_TOKEN` or `GITHUB_TOKEN`. Implemented with stdlib `urllib` (so it works even without
   `gh` *or* `curl` installed); conceptually the same as `curl -H "Authorization: Bearer $TOKEN"`.

If none are available, the work is **preserved, not lost** (see each skill below).

## `distill-plugin` (filing issues) — mostly automatic

`distill/emit.py` already implements transports 1 and 3 and **auto-selects**: `gh` if installed,
else the REST API if a token is set, else it **defers** — writing the (already-redacted) issue to
`~/.claude/talon-distill/pending/<fp>.md` for later. So in most environments you just run `emit.py`
and it does the right thing.

To use the **MCP** transport (transport 2) — e.g. you have MCP tools but no `gh`/token, or you
simply prefer them:

1. Run `emit.py` with `TALON_DISTILL_DRY_RUN=1`. This still runs the **redaction gate** (scrub +
   quarantine) and computes the fingerprint, and logs the intended issue (title/body/repo) instead
   of posting. **Never post a body that hasn't been through `emit.py` first** — that gate is the
   only thing keeping secrets out of public issues.
2. Then, via the MCP tools, reproduce `emit.py`'s dedup: search the repo for the fingerprint
   (`<!-- distill-fp: … -->`); if none → create the issue with the logged body + `distillation`
   label; if an open one matches → add a comment; if a closed one matches → reopen + comment.

## `onboard-plugin` (raising PRs)

Branch creation and `git push` use plain **git** (no `gh` needed). Only opening the PR is
transport-specific — prefer in the same order:

1. `gh pr create --repo <owner>/<repo> --base <branch> --head <branch> --title … --body …`
2. GitHub MCP `create_pull_request` (owner, repo, base, head, title, body).
3. REST API: `POST https://api.github.com/repos/<owner>/<repo>/pulls` with
   `{"title","head","base","body"}` and an `Authorization: Bearer $GH_TOKEN` header
   (equivalently `curl`).

## Token setup (for the REST API path)

```bash
export GH_TOKEN=ghp_xxx      # a fine-grained or classic PAT with `repo` (issues + PRs) scope
# or GITHUB_TOKEN
```
`gh auth token` prints one if `gh` is configured. Keep tokens out of the repo and out of issue
bodies (the scrubber flags `ghp_…` shapes, but don't rely on it).
