---
name: onboard-plugin
description: >-
  Onboard a NEW plugin into the Talon plugin marketplace (github.com/falconh/talon), or RELEASE
  AN UPDATE to a plugin already listed there, with correct dual Claude Code + Codex support. Use
  this WHENEVER the user wants to add, list, publish, or onboard a plugin/skill to Talon; update,
  bump, re-pin, or cut a release of a plugin in Talon; make a plugin work with both Claude Code and
  Codex; or asks about Talon's structure, the plugin repo naming convention, or the release/version
  process — even if they don't say "Talon" explicitly but reference the marketplace, its catalogs
  (.claude-plugin/marketplace.json or .agents/plugins/marketplace.json), or onboarding a skill.
  Enforces the talon-<name> repo naming convention, the dual manifests + shared SKILL.md, keeping
  BOTH marketplace catalogs in sync, semver version bumping + git tagging, and raising every change
  as a pull request.
---

# Onboard / update a Talon marketplace plugin

Talon (`github.com/falconh/talon`) is a single repo that acts as a plugin marketplace for **both
Claude Code and Codex** at once. The two ecosystems use different catalog files and different plugin
manifests, but they load the **same `SKILL.md` files**. This skill keeps both sides correct and in
sync while you add a plugin or ship an update.

## Mental model

A plugin is described twice (once per tool) but its behaviour lives once:

| | Claude Code | Codex |
| --- | --- | --- |
| Marketplace catalog (in `talon/`) | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` |
| Plugin manifest (in the plugin) | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` |
| Skills (shared, one copy) | `skills/<skill>/SKILL.md` | same file (`"skills": "./skills/"`) |
| Add the marketplace | `/plugin marketplace add falconh/talon` | `codex plugin marketplace add falconh/talon` |
| Install / enable | `/plugin install <name>@talon` | enable in `/plugins` |

A plugin can live **inside talon** (a *local* source under `plugins/<name>/`) or **in its own repo**
(a *remote* source referenced from the catalogs). Prefer a **remote** source when the plugin is
substantial or independently useful — it keeps a single source of truth and lets the plugin be
versioned and tagged on its own. Use a **local** source for small, talon-specific plugins (like this
one).

## Golden rules (do not skip)

These exist because a marketplace that is half-updated silently breaks for one tool while looking
fine for the other.

1. **Every change is a pull request.** Never push to a default branch (`main`/`master`). Branch,
   commit, push the branch, and open a PR with `gh pr create`. This applies to both the plugin repo
   and to talon.
2. **Both catalogs always move together.** If a plugin appears in one catalog it must appear in the
   other. If you change a version/ref in one, change it in the other in the same PR.
3. **Every plugin ships both manifests + a dual-valid skill.** A plugin needs both
   `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, and every `SKILL.md` frontmatter
   must contain **both `name` and `description`** (Codex *requires* `name`; Claude Code uses
   `description`). A skill missing `name` is invisible to Codex.
4. **A release means: bump → tag → pin.** Bump the `version` in both plugin manifests (semver), tag
   the plugin repo `vX.Y.Z`, then pin both talon catalog entries to that tag. Claude Code only
   delivers updates to users when the manifest `version` changes, so the bump is what makes an
   update real — not just new commits.
5. **Follow the repo naming convention** (below) for new plugin repos.

## Naming convention

- **Plugin repository:** `talon-<name>` (kebab-case), e.g. `talon-terraform-module-steering`,
  `talon-aws-cost-report`. The `talon-` prefix groups all marketplace plugins in the GitHub account,
  makes them searchable, and avoids collisions. *(Existing repos created before this convention —
  e.g. `terraform-module-steering` — are grandfathered. Rename them only if you also update the
  `repo`/`url` in both talon catalogs, in the same PR.)*
- **Plugin `name`** (in both manifests and both catalog entries): `<name>` **without** the `talon-`
  prefix, e.g. `terraform-module-steering`. This keeps install/invocation names clean
  (`/plugin install terraform-module-steering@talon`).
- **Skill folder / `name`:** short kebab-case describing the action (`onboard-plugin`,
  `cost-report`), not the plugin. Invocation becomes `/<plugin>:<skill>`.

## Before you start

Confirm the GitHub CLI is ready: `gh auth status` (needs `repo` scope). All steps below use `gh`.

Decide which flow you are in:
- **Flow A — onboard a new plugin** (it is not yet in talon's catalogs).
- **Flow B — release an update** (the plugin is already listed; you are shipping a new version or a
  re-pin).

The exact JSON for every manifest and catalog entry — local and remote — is in
[`references/templates.md`](references/templates.md). The end-to-end command sequence with `gh` is in
[`references/release-and-pr-workflow.md`](references/release-and-pr-workflow.md). Read the relevant
one as you go rather than reproducing JSON from memory.

## Flow A — onboard a new plugin

1. **Inspect the plugin.** Read its repo (or local dir). Determine: does it already have a
   `.claude-plugin/plugin.json`? a `.codex-plugin/plugin.json`? Do its `SKILL.md` files have both
   `name` and `description`? What is its current `version` and default branch?

2. **Make it dual-compatible (a PR on the plugin repo, if changes are needed).** If the plugin is
   missing the Codex manifest, add `.codex-plugin/plugin.json` mirroring the Claude one over the
   same `skills/` directory (template in `references/templates.md`). If any `SKILL.md` lacks `name`,
   add it. Bump the plugin `version` for this change (it is a real, user-visible change) and follow
   the release steps (Flow B steps 2–4) to bump, tag, and pin. The skill body itself usually needs
   no changes — only the manifests.

3. **Choose the source type.** Remote (its own repo, recommended for real plugins) or local
   (vendored under `talon/plugins/<name>/`). For remote, make sure a release tag exists (Flow B
   step 3) so you can pin to it.

4. **Add entries to BOTH catalogs (a PR on talon).** Add a plugin entry to
   `.claude-plugin/marketplace.json` and a matching entry to `.agents/plugins/marketplace.json`,
   using the templates. For a remote source, pin `ref` to the release tag `vX.Y.Z` and set the
   Claude entry's `version` to match. Update the README's plugins table if there is one.

5. **Verify**, then open the PR (see Verification below).

## Flow B — release an update (bump → tag → pin)

Use this whenever a plugin's content changes, or you are adding Codex support, or re-pinning talon.

1. **Land the content change on the plugin repo via PR.** Branch, make the change, push, open a PR,
   and merge it. Do not tag yet.

2. **Bump `version` in BOTH plugin manifests** (`.claude-plugin/plugin.json` and
   `.codex-plugin/plugin.json`) using semver:
   - **patch** (`x.y.Z`): docs, fixes, no behaviour change for consumers.
   - **minor** (`x.Y.0`): additive — new skill, new capability, **adding Codex support**.
   - **major** (`X.0.0`): breaking — removed/renamed skill, changed inputs/behaviour.
   Keep the two manifests on the **same** version. (This bump can be part of the step-1 PR.)

3. **Tag the release on the plugin repo.** After the version-bump commit is on the default branch,
   create an **annotated** tag matching the existing convention (`v`-prefixed) and push it:
   `git tag -a vX.Y.Z -m "vX.Y.Z — <summary>" <sha> && git push origin vX.Y.Z`.

4. **Pin talon to the new tag (a PR on talon).** In **both** catalogs, set the plugin entry's
   `source.ref` to `vX.Y.Z`. In the Claude catalog also set the entry's `version` to `X.Y.Z`. This
   makes talon serve exactly the tagged release and is what propagates the update to users
   (`/plugin marketplace update talon` / `codex plugin marketplace upgrade talon`).

5. **Verify**, then open the PR.

## Verification (before every PR)

Run the bundled validator against the talon checkout — it confirms both catalogs parse, every plugin
is present in **both** catalogs, local plugins have both manifests and dual-valid skills, and remote
entries are pinned to a tag (not a bare branch):

```bash
python3 skills/onboard-plugin/scripts/validate_talon.py --root .
```

Also sanity-check by hand:
- Every touched `*.json` parses.
- For a remote release: the tag exists on the plugin repo
  (`gh api repos/<owner>/<repo>/git/ref/tags/vX.Y.Z`) so the pin resolves.
- If available: `claude plugin validate plugins/<name>` for local plugins.

Only open the PR once verification passes. Put both catalog edits (and any README/table update) in
the **same** PR so the two tools never drift.

## Quick reference

- Manifest + catalog JSON (local and remote, both tools): `references/templates.md`
- Branch/PR/tag command sequence with `gh`: `references/release-and-pr-workflow.md`
- Validator: `scripts/validate_talon.py`
