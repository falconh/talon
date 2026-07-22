# Release & PR workflow

Every change to a plugin repo or to the marketplace goes through a pull request. Never commit to a default
branch. This file gives the exact command sequence; the conceptual steps are in `SKILL.md`.

`git` is always required. The PR-creation commands below show `gh` as the primary example; for the
`gh`-not-installed backends (GitHub MCP server / REST API), see `github-access.md` in this directory
(SKILL.md → *Before you start* covers picking the backend).

**Repo slug and default branch are placeholders.** `<marketplace-repo>` / `<owner>/<repo>` and
`<default-branch>` come from `scripts/resolve_marketplace.py` and the user's confirmation (SKILL.md →
*Before you start*). Never hardcode a marketplace, and **never assume the default branch is `main`** —
resolve it (many repos, Talon included, default to `master`).

**Push access vs. fork.** These commands assume you can push to the target repo. If you can't — you're
contributing a plugin to a marketplace (or plugin repo) you don't own — you must **fork first**, push
your branch to the fork, and open the PR from the fork. Check with
`gh repo view <owner>/<repo> --json viewerPermission` (`WRITE`/`MAINTAIN`/`ADMIN` = push directly;
`READ`/none = fork), then follow the fork sequence in
`github-access.md` in this directory (*Push access vs. fork*).

End commit messages and PR bodies with the standard trailer if your environment requires it.

## A. Change a plugin repo (content, manifests, version bump)

```bash
# in a clone of the plugin repo
git checkout -b <topic-branch>

# ... edit files: content, and bump "version" in BOTH manifests ...
#   .claude-plugin/plugin.json   -> "version": "X.Y.Z"
#   .codex-plugin/plugin.json    -> "version": "X.Y.Z"   (add this file if missing)

git add -A
git commit -m "<summary>"
git push -u origin <topic-branch>

# open the PR — gh shown; no gh? use MCP or the REST API (see github-access.md):
gh pr create --repo <owner>/<repo> \
  --base <default-branch> \
  --title "<summary>" \
  --body  "<what changed and why; note the version bump X.Y-1 -> X.Y.Z>"
```

After the PR is **merged**, tag the release on the merge commit:

```bash
git fetch origin
git tag -a vX.Y.Z -m "vX.Y.Z — <summary>" origin/<default-branch>
git push origin vX.Y.Z
# confirm it resolves (pure git, no gh needed):
git ls-remote --tags origin refs/tags/vX.Y.Z
```

Tags are `v`-prefixed and **annotated** (`-a`), matching the existing convention.

## B. Update the marketplace catalogs (onboard, or re-pin to a new tag)

`<marketplace-repo>` and `<marketplace-default-branch>` below are the confirmed marketplace and its
resolved default branch (from `scripts/resolve_marketplace.py`). If you lack push access to the
marketplace, fork it first and push to the fork (see the header note + `github-access.md`).

```bash
# in a clone/worktree of the marketplace repo (<marketplace-repo>)
git checkout -b <topic-branch>

# ... edit BOTH catalogs together ...
#   .claude-plugin/marketplace.json   -> add/replace the plugin entry (ref + version)
#   .agents/plugins/marketplace.json  -> add/replace the matching entry (ref)
#   README.md                         -> update the plugins table if present

# path relative to this skill's directory; --root is the checkout being validated (here, cwd):
python3 <skill-dir>/scripts/validate_talon.py --root .

git add -A
git commit -m "<summary>"
git push -u origin <topic-branch>          # origin = your fork if you forked

# open the PR — gh shown; no gh? use MCP or the REST API (see github-access.md):
gh pr create --repo <marketplace-repo> \
  --base <marketplace-default-branch> \
  --title "<summary>" \
  --body  "<which plugin, local vs remote, pinned tag>"
# forked? add:  --head <your-github-login>:<topic-branch>
```

## Ordering for a brand-new remote plugin

1. PR on the plugin repo: add/confirm both manifests + dual-valid skills, set/bump `version`. Merge.
2. Tag `vX.Y.Z` on the plugin repo (section A).
3. PR on the marketplace: add both catalog entries pinned to `vX.Y.Z` (section B). Merge.

## Ordering for an update to an existing remote plugin

1. PR on the plugin repo: change + version bump. Merge.
2. Tag the new `vX.Y.Z`.
3. PR on the marketplace: re-pin both entries' `ref` (and the Claude entry `version`) to the new tag. Merge.

## Why this order

The marketplace's entries pin a tag, so the tag must exist before the marketplace PR can point at it. The version bump
must be on the plugin repo before tagging, because the tag should capture the bumped manifests.
Claude Code gates user-visible updates on the manifest `version`, which is why a re-pin without a
version bump does **not** reach users as an update.
