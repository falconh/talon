# GitHub access — backends & order

How this skill reaches GitHub to open a PR. `git` itself (branch, commit, push) never needs any of
this; only *opening the PR* is transport-specific.

> This file lives **inside the skill** on purpose. A harness's install unit may be the *skill*, not
> the plugin (Codex installs skills flat under `~/.agents/skills/<skill>/`), so a reference kept at
> the plugin root would not ship with the skill. The shared backend list is therefore duplicated
> with the plugin-level `references/github-access.md` used by `skill-feedback` — that duplication is
> the deliberate cost of each skill being self-contained.

Three transports, tried in this order:

1. **`gh` CLI** — used if `gh` is on `PATH` and authenticated (`gh auth status`; needs `repo` scope).
   Simplest; no token handling.
2. **GitHub MCP server** — if the session exposes GitHub MCP tools (e.g. `mcp__github__*` /
   `create_pull_request`). These are **agent-level** tools (only the model can call them — a script
   cannot), so drive them from the skill, not from helper code.
3. **REST API (last resort)** — a direct HTTPS call to `https://api.github.com` with a token from
   `GH_TOKEN` or `GITHUB_TOKEN`.

## Opening the PR

1. `gh pr create --repo <owner>/<repo> --base <branch> --head <branch> --title … --body …`
2. GitHub MCP `create_pull_request` (owner, repo, base, head, title, body).
3. REST: `POST https://api.github.com/repos/<owner>/<repo>/pulls` with `{"title","head","base","body"}`
   and an `Authorization: Bearer $GH_TOKEN` header (equivalently `curl`).

## Push access vs. fork (contributor flow)

A marketplace is meant to take plugins from **anyone** via PR, and most contributors don't have push
access to the marketplace repo. Decide the path before you push:

```bash
gh repo view <owner>/<repo> --json viewerPermission -q .viewerPermission
#  WRITE / MAINTAIN / ADMIN  -> you can push a branch to the repo directly
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

## Contributor who also can't tag the plugin's own repo → use a LOCAL source

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
export GH_TOKEN=ghp_xxx      # a fine-grained or classic PAT with `repo` (PRs) scope
# or GITHUB_TOKEN
```
`gh auth token` prints one if `gh` is configured. Keep tokens out of the repo and out of PR bodies.
