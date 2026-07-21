# onboard-plugin — Provider-Agnostic Skill — Design

**Status:** In progress (Phases 1–2 implemented) · **Date:** 2026-07-22 · **Owner:** falconh
**Base:** `origin/master` @ merge of #19 · **Branch:** `provider-agnostic-phase1` (PR #20)
**Touches:** `plugins/plugin-manager/skills/onboard-plugin/` (SKILL.md, `scripts/resolve_marketplace.py`,
`references/{github-access,templates,release-and-pr-workflow}.md`) and the plugin-level
`plugins/plugin-manager/references/github-access.md` (split). **No** catalog/manifest/version change.

## Problem & Goal

`onboard-plugin`'s job — get a plugin into a GitHub-hosted **dual Claude Code + Codex** marketplace's
catalogs, and cut releases (bump → tag → pin) — is **git + GitHub** work, provider-independent by
construction. Yet the skill had picked up dependencies on one harness's plumbing:

1. **`${CLAUDE_PLUGIN_ROOT}`** — a Claude Code-only variable used to locate the skill's own bundled
   scripts and reference docs. Codex sets no variable by that name; it also isn't exported into an
   ad-hoc shell (it is an *agent-resolved placeholder*, set by Claude only for skill/hook execution).
2. **Install-unit assumption.** A *plugin-level* reference (`references/github-access.md`, shared with
   `skill-feedback`) sat one level above the skill. Under Claude that ships because the install unit
   is the **plugin**; under Codex the install unit is the **skill** (flat `~/.agents/skills/<skill>/`),
   so a plugin-level file **would not ship with the skill at all**.
3. **Self-location** read only Claude's `~/.claude/plugins/known_marketplaces.json`, so on Codex the
   "which marketplace did I come from?" default always degraded to asking the user.

**Goal:** the same skill runs correctly under **any** skill-supporting harness — Claude Code, Codex,
and unknown future ones — with no per-run branching by the reader. Convenience (auto-detected
default) may vary per harness; **correctness must not**.

## Verified facts (why the design is shaped this way)

Inspected on the maintainer's machine:

| | Claude Code | Codex |
| --- | --- | --- |
| Plugin-root env var | `$CLAUDE_PLUGIN_ROOT` (skill/hook exec only; empty in ad-hoc shell) | none |
| Install unit & layout | whole **plugin** under `~/.claude/plugins/{marketplaces,cache}/<mkt>/plugins/<plugin>/skills/<skill>/` | flat **skill** under `~/.agents/skills/<skill>/` |
| Installed registry | `~/.claude/plugins/known_marketplaces.json` (name → slug) | `~/.agents/.skill-lock.json` (`skills.<name>.source` = `owner/repo` slug, + `pluginName`, `skillPath`) |

The Codex `.skill-lock.json` maps each installed skill directly to its `source` slug — cleaner than
Claude's name→slug indirection.

## Design: a provider-neutral core + thin adapters

**Leading idea (ports & adapters):** keep a provider-neutral **core** and isolate each place a harness
genuinely differs behind a small **adapter**. ~90% of the skill is already core.

**Neutral core (unchanged):** bump → tag → pin, semver, PR-only discipline, git, `gh`/MCP/REST PR
creation (that is *environment* variance, not provider), the dual-catalog/dual-manifest invariant,
target-confirmation, and default-branch via `git ls-remote`.

**Three seams → adapters:**

| Seam | Provider-specific part | Adapter / fix |
| --- | --- | --- |
| **1. Locate bundled files** | `$CLAUDE_PLUGIN_ROOT`; plugin-vs-skill install unit | Reference every file **relative to the skill's own directory**, and keep **every** referenced file **inside** that directory (so the install unit carries it under any harness). |
| **2. Self-detect root marketplace** | which installed-registry exists | Resolver tries each known registry (Claude `known_marketplaces.json`, then Codex `.skill-lock.json`), else git-remote-of-checkout, else ask. |
| **3. CLI command names** | `/plugin …` vs `codex plugin …` | Already dual-listed in the mental-model table (Phase 3, optional). |

### The load-bearing invariant: *scripts accelerate, prose suffices*

Two things are intrinsically per-harness and cannot be fully generalized in code: **(a)** how the agent
learns its own skill directory, and **(b)** native self-location from a harness's registry. The design
survives an *arbitrary* harness — including one that can't run bundled Python at all — because every
script-backed step also states its logic in prose (the resolver's fallback chain; the validator's four
checks). A script-less harness performs them by hand rather than dead-ending. Scripts are an
accelerator, never a dependency.

This yields a **two-tier portability contract**:

- **Tier 1 — universal (any skill harness, no new code):** files bundled inside the skill dir;
  identity from git-remote / `marketplace.config.json` / `--repo`; **user-confirm as the backstop**.
  An unknown harness stays correct — it just asks instead of auto-detecting.
- **Tier 2 — per-harness adapter (opt-in convenience):** ~30 lines to read that harness's registry so
  its users get an auto-detected default. Never required for correctness.

## Implementation status

**Phase 1 — self-contained + harness-neutral files (done, PR #20):**
- All paths are skill-dir-relative; all referenced files live inside the skill.
- `github-access.md` **split**: onboard-plugin's copy moved into
  `skills/onboard-plugin/references/github-access.md`; the plugin-root copy trimmed to the
  `skill-feedback` material (its only other consumer — verified nothing in `distill/` reads the
  markdown and `skill-feedback/SKILL.md` never linked it). Shared backend list duplicated **by
  design** (per-skill install units), noted in both files.
- All 9 `${CLAUDE_PLUGIN_ROOT}` usages retired; one optional, non-load-bearing Claude hint remains.
- Added the *scripts accelerate, prose suffices* invariant.
- **Acceptance:** no load-bearing token; all 6 referenced files resolve inside the skill dir; no
  reference escapes it; validator 0/0; resolver output unchanged.

**Phase 2 — dual-registry self-location (done, PR #20):**
- `marketplace_from_self_location` → `marketplace_from_claude_registry` (Claude), new
  `marketplace_from_codex_lock` (Codex `.skill-lock.json`; match by skill-name key, else `skillPath`
  suffix; prefer slug-shaped `source`, else parse `sourceUrl`).
- `main()` tries Claude then Codex; `--known-marketplaces` / `--skill-lock` overrides make both paths
  unit-testable.
- **Verified:** 6-case adapter unit suite passes; Codex-sim CLI resolves via a fixture lock
  (`source=self-location-codex`, live `master`); Claude/git path unchanged; unresolvable →
  `resolved:false` (ask). Validator 0/0.

**Phase 3 — optional polish (not started):** one provider-command table; in the body, soften "dual
Claude Code + Codex" toward "any harness with a dual catalog" while keeping both named in the
*description* for trigger reliability.

## Non-goals / deferred

- `skill-feedback` / `distill` provider-agnosticism — Talon-coupled (`registry.py` hard-filters to
  `talon`) and reliant on Claude-only **hooks** (a separate provider concept). Out of scope.
- Porting scripts off `python3` — a prior explicit decision to keep `python3`.
- Remote-plugin caveat for Codex self-location: `.skill-lock.json`'s `source` is the *install-source*
  repo, which equals the marketplace only when the skill lives in the marketplace it manages (the
  common self-hosting case, incl. onboard-plugin). For a remote plugin whose source repo differs from
  its marketplace it may be the plugin repo — acceptable because it is a *default the user confirms*.

## Validation (done)

**`/writing-great-skills` review:** the combined Phase 1+2 change is well-formed — no required edits.
The two new *Before you start* paragraphs are legitimate always-loaded reference (not no-ops), the
`github-access.md` duplication is intentional and documented, and the "scripts accelerate" invariant is
backed by real prose (resolver fallback order + the validator's four checks), not a hollow claim.

**`/skill-creator` eval (iteration 2):** `evals/evals.json` gained 3 provider-agnostic cases (6 Codex
self-contained, 7 no-python manual verify, 8 unknown-harness) plus assertions on all 8. Each was run by
an independent subagent following the skill (with-skill = this branch; baseline = pre-change
`origin/master`), then graded against its assertions.

| Eval | with-skill | baseline (old) |
| --- | --- | --- |
| 6 codex-self-contained-onboard | 5/5 | 2/5 |
| 7 no-python-manual-verify | 3/3 | 1/3 |
| 8 unknown-harness-onboard | 3/3 | 2/3 |
| 2 unnamed-marketplace-confirm | 4/4 | regression (with-skill only) |
| 3 contributor-fork-no-write-access | 5/5 | regression (with-skill only) |

**Result: the change passes — with-skill 20/20 (100%); baseline 5/11 (45%) on the provider-agnostic
evals**, a +0.53 pass-rate delta on evals 6–8. The delta is exactly the three fixes: baseline agents,
following the *old* skill, independently reported that (a) the `${CLAUDE_PLUGIN_ROOT}/skills/onboard-plugin/`
script prefix "must be dropped" under a flat install, (b) `github-access.md` is **unreachable** under
Codex's flat layout, and (c) the old skill has no Codex self-location and presents the validator as
required — validating both the eval design and the fixes.
