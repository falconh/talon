# Release & PR workflow (with `gh`)

Every change to a plugin repo or to talon goes through a pull request. Never commit to a default
branch. This file gives the exact command sequence; the conceptual steps are in `SKILL.md`.

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

gh pr create --repo falconh/<repo> \
  --base <default-branch> \
  --title "<summary>" \
  --body  "<what changed and why; note the version bump X.Y-1 -> X.Y.Z>"
```

After the PR is **merged**, tag the release on the merge commit:

```bash
git fetch origin
git tag -a vX.Y.Z -m "vX.Y.Z — <summary>" origin/<default-branch>
git push origin vX.Y.Z
# confirm it resolves:
gh api repos/falconh/<repo>/git/ref/tags/vX.Y.Z -q '.ref'
```

Tags are `v`-prefixed and **annotated** (`-a`), matching the existing convention.

## B. Update talon catalogs (onboard, or re-pin to a new tag)

```bash
# in a clone/worktree of falconh/talon
git checkout -b <topic-branch>

# ... edit BOTH catalogs together ...
#   .claude-plugin/marketplace.json   -> add/replace the plugin entry (ref + version)
#   .agents/plugins/marketplace.json  -> add/replace the matching entry (ref)
#   README.md                         -> update the plugins table if present

python3 plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py --root .

git add -A
git commit -m "<summary>"
git push -u origin <topic-branch>

gh pr create --repo falconh/talon \
  --base main \
  --title "<summary>" \
  --body  "<which plugin, local vs remote, pinned tag>"
```

## Ordering for a brand-new remote plugin

1. PR on the plugin repo: add/confirm both manifests + dual-valid skills, set/bump `version`. Merge.
2. Tag `vX.Y.Z` on the plugin repo (section A).
3. PR on talon: add both catalog entries pinned to `vX.Y.Z` (section B). Merge.

## Ordering for an update to an existing remote plugin

1. PR on the plugin repo: change + version bump. Merge.
2. Tag the new `vX.Y.Z`.
3. PR on talon: re-pin both entries' `ref` (and the Claude entry `version`) to the new tag. Merge.

## Why this order

Talon entries pin a tag, so the tag must exist before the talon PR can point at it. The version bump
must be on the plugin repo before tagging, because the tag should capture the bumped manifests.
Claude Code gates user-visible updates on the manifest `version`, which is why a re-pin without a
version bump does **not** reach users as an update.
