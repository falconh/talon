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

## `skill-feedback` (filing issues) — mostly automatic

`feedback_emit.py` already implements transports 1 and 3 and **auto-selects**: `gh` if installed,
else the REST API if a token is set, else it **defers** — writing the (already-redacted) issue to
`~/.claude/talon-distill/pending/<timestamp>-<id>.md` for later. So in most environments you just
run `feedback_emit.py` and it does the right thing. There's no dedup/fingerprint lookup here — a
human approves every finding before it's ever filed, so each run either opens a fresh issue or
defers; it never searches for or comments on an existing one.

To use the **MCP** transport (transport 2) — e.g. you have MCP tools but no `gh`/token, or you
simply prefer them:

1. Run `feedback_emit.py` (optionally with `TALON_DISTILL_DRY_RUN=1` to rehearse first). This still
   runs the **redaction gate** (scrub + quarantine) before anything else. **Never post a body that
   hasn't been through `feedback_emit.py` first** — that gate is the only thing keeping secrets out
   of public issues.
2. If the result was `deferred`, read the queued (already-redacted) draft from
   `~/.claude/talon-distill/pending/` and create the issue via the MCP tools with that title/body,
   unchanged, plus the `distill-feedback` label.

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
