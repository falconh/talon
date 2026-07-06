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

### Push access vs. fork (contributor flow)

A marketplace is meant to take plugins from **anyone** via PR, and most contributors don't have push
access to the marketplace repo. Decide the path before you push:

```bash
gh repo view <owner>/<repo> --json viewerPermission -q .viewerPermission
#  WRITE / MAINTAIN / ADMIN  -> you can push a branch to the repo directly (the flow above)
#  READ / (empty / error)    -> you must fork first
```
(No `gh`? A `403` on `git push` to the upstream means the same thing — fork.)

**Fork flow** (no write access):

```bash
# 1. fork + clone in one step (origin = your fork, upstream = the marketplace)
gh repo fork <owner>/<repo> --clone --remote
cd <repo>

# 2. branch, edit BOTH catalogs, validate, commit
git checkout -b <topic-branch>
# ... edits ...
git commit -am "<summary>"

# 3. push to YOUR fork, then open the PR against upstream's default branch
git push -u origin <topic-branch>
gh pr create --repo <owner>/<repo> \
  --base <default-branch> \
  --head <your-github-login>:<topic-branch> \
  --title "<summary>" --body "<…>"
```

Without `gh`: create the fork via the REST API (`POST /repos/<owner>/<repo>/forks`) or the GitHub
MCP `fork_repository` tool, add it as a remote (`git remote add fork
https://github.com/<you>/<repo>.git`), push there, then open the PR with `head` set to
`<your-github-login>:<topic-branch>`. The base repo/branch are still `<owner>/<repo>` /
`<default-branch>` (resolve the branch with `scripts/resolve_marketplace.py`, never assume `main`).

### Contributor who also can't tag the plugin's own repo → use a LOCAL source

A **remote** catalog entry pins to a release **tag** (`vX.Y.Z`) on the plugin's own repo — which only
someone with push access to that repo can create. So if you're a contributor who lacks push/tag
access to the **plugin's** repo (not just the marketplace), you *cannot complete* a remote pin: the
tag you'd point at can't be made. Don't produce that dead-end plan. Instead **vendor the plugin as a
`local` source** inside your marketplace-fork PR (copy it under `plugins/<name>/` and use the local
catalog entries from `references/templates.md`), which needs no tag and is fully completable by a
read-only contributor. Whoever owns the plugin can later cut a real tag and the marketplace can
switch the entry from `local` to a pinned `remote` source. (If you *do* have push access to the
plugin repo, prefer the remote source as usual — single source of truth, independently versioned.)

## Token setup (for the REST API path)

```bash
export GH_TOKEN=ghp_xxx      # a fine-grained or classic PAT with `repo` (issues + PRs) scope
# or GITHUB_TOKEN
```
`gh auth token` prints one if `gh` is configured. Keep tokens out of the repo and out of issue
bodies (the scrubber flags `ghp_…` shapes, but don't rely on it).
