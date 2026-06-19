# Talon Plugin Distillation — Design

**Status:** Approved (design phase) · **Date:** 2026-06-17 · **Owner:** falconh

## Problem & Goal

Talon-marketplace plugins (skills/hooks installed from `github.com/falconh/talon`) are
used in real sessions, but nothing closes the loop from "how a plugin actually behaved
in a session" back to "how the plugin should be improved." We want to:

- Automatically learn from every session where a Talon plugin was **used**, *or where it
  **should** have been used but wasn't* (under-trigger).
- Surface **concrete, plugin-specific** improvements.
- Deliver them as GitHub issues on the plugin's own repo.
- Do all of this **without leaking session content** to a public issue tracker.

"Distillation" here is shorthand for: reflect on real usage and emit improvement findings.

## Non-goals

- Auto-editing or auto-PRing skills. Output is an *issue* (a recommendation); the human
  applies changes through the existing PR-only onboard-plugin flow.
- Distillation for non-Talon plugins. Scope is keys ending in `@talon` in the local
  install registry.
- A Codex-side automatic trigger. Codex does not fire `SessionEnd` hooks the same way;
  the automatic capture path is Claude-Code-only. The manual `distill-plugin` path works
  anywhere the skill can be invoked.

## Reference

Architecture validated against **AMAP-ML/SkillClaw** (session capture + Summarize →
Aggregate → Execute evolve pipeline, 4-way decision, per-skill batching). Key divergence:
SkillClaw writes to *private* storage and does no secret scrubbing; our public-repo target
makes redaction mandatory (see §7).

---

## 1. Packaging

Rebrand `talon-onboarding` → **`talon-plugin-manager`**, containing:

| Path | Role |
|------|------|
| `skills/onboard-plugin/` | Existing maintainer skill (unchanged behavior). |
| `skills/distill-plugin/`  | New — on-demand entry point + the documented pipeline (Phase B). |
| `hooks/`                  | `SessionEnd` hook — capture only (Phase A). |

The rename is a **major version bump**, propagated to **both** manifests
(`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`) and **both** catalogs
(Claude + Codex), then re-pinned via onboard-plugin **Flow B** (bump → tag → pin, PR-only).
Skill *names* stay stable to avoid breaking installs (golden rule #5).

---

## 2. Two-phase architecture (core)

SkillClaw's lesson: **capture is cheap and per-session; analysis is expensive and batched.**

```
            every session                         threshold crossed
  ┌───────────────────────────┐          ┌──────────────────────────────┐
  │ Phase A — Capture (no LLM) │  append  │ Phase B — Distill (batched,   │
  │ SessionEnd hook script     │ ───────▶ │ LLM): Summarize → Aggregate → │
  │ → evidence/<plugin>.jsonl  │          │ Decide → Classify → Redact →  │
  └───────────────────────────┘          │ Emit GitHub issue             │
                                          └──────────────────────────────┘
```

### Phase A — Capture (every session, deterministic, no LLM)

`SessionEnd` hook runs a fast script that:

1. Reads hook stdin JSON: `session_id`, `cwd`, `transcript_path`.
2. Loads the **Talon registry** = keys ending in `@talon` from
   `~/.claude/plugins/installed_plugins.json`.
3. Parses the transcript JSONL for:
   - `Skill` / Bash tool-calls matching a Talon plugin → **usage**.
   - Domain activity matching the domain-signal map (§5) with **no** Talon skill fired →
     **under-trigger candidate**.
   (Prompt-time injection alone is not treated as usage — only an actual read/run counts.)
4. Runs the **deterministic friction pre-scan** and emits structured hints:
   `has_tool_errors`, `skills_referenced`, `repeated_error_count`, and
   `retry` / `correction` / `abandonment` flags.
5. Appends one compact evidence record (JSON) to the rolling per-plugin store:
   `~/.claude/talon-distill/evidence/<plugin>.jsonl`.
6. If the store crosses the **batch threshold** (N sessions, or a finding-cluster recurs
   ≥K), it spawns Phase B headless in the background (`claude -p`). Hooks cannot invoke a
   skill, so this is the automatic bridge; if spawning is unavailable, the queue simply
   waits for the next manual `distill-plugin` run.

**Friction signals (the pre-scan gate):**
- *Hard (fire immediately):* plugin script exits non-zero / tool result `is_error`;
  the same tool error occurs ≥2×.
- *Soft (need ≥2 accumulated, or 1 + proximity):* correction language, retries,
  task abandonment.

### Phase B — Distill pass (batched, LLM)

Identical whether auto-spawned by the hook or run via the `distill-plugin` skill:

1. **Summarize.** Build a deterministic, clipped, lossless **trajectory** per session
   (tool calls with ✓/✗ outcomes, skills referenced, ~400-char clips). Run the reflection
   LLM on the **trajectory**, never the raw transcript. Reflection is abstraction-first and
   is fed the Phase-A friction hints.
2. **Aggregate.** Group session evidence **per plugin** and **per finding-cluster**.
   Recurrence count = evidence strength (this is the batched aggregate-then-decide model —
   we decide once from N sessions, not once per session).
3. **Decide (4-way, once per finding-cluster):**
   `improve_skill` / `optimize_description` / `create_skill` / `skip`.
4. **Classify fault** *before* committing a decision: was the friction the **plugin's**
   fault, the **agent's**, or the **environment's**? Only plugin-fault findings proceed.
   *When in doubt, `skip`.*
5. **Redact** (§7).
6. **Emit / update** the GitHub issue (§7).

---

## 3. Finding-type → detection mapping

| Detection | Likely decision |
|-----------|-----------------|
| Usage-gated friction (plugin used, went badly) | `improve_skill` / `optimize_description` |
| Under-trigger (domain activity, no Talon skill fired — SkillClaw's `NO_SKILL` bucket) | `create_skill`, or "should have triggered" → `optimize_description` |

---

## 4. Decision taxonomy (adopted from SkillClaw)

- **`improve_skill`** — body/guidance is wrong, missing, or misleading. Targeted edit.
- **`optimize_description`** — skill is right but under/over-triggers; fix the description
  (skill-creator's lane; harvest failing prompts into evals — §8).
- **`create_skill`** — recurring domain work that no skill covers.
- **`skip`** — below threshold, agent/environment fault, or ambiguous.

Guardrails carried over: conservative editing, no generic best-practice bloat, don't
remove correct content, prefer surgical changes, and bias toward `skip`.

---

## 5. Domain-signal map (hybrid)

Used to detect under-trigger (domain activity with no skill firing).

- **Self-declared:** a per-plugin `distill.json` with `domain_globs` (e.g. `**/*.tf`) and
  `domain_cmds` (e.g. `terraform`, `tofu`) when the author provides it.
- **Inferred fallback:** when absent, infer signals from the skill description via LLM.
- onboard-plugin **offers** to capture `distill.json` at onboarding (non-blocking).

---

## 6. Batch trigger & state

- Evidence store: `~/.claude/talon-distill/evidence/<plugin>.jsonl` (append-only).
- Threshold: N sessions per plugin **or** a finding-cluster recurring ≥K — tunable.
- Auto-run: hook spawns `claude -p` headless when threshold crosses; otherwise deferred to
  manual `distill-plugin`.
- Processed records are marked/rotated so Phase B does not re-judge the same session.

---

## 7. Redaction (public-redaction-gated) & output

Three layers, defense-in-depth, because the destination is a **public** repo:

- **L1 — Abstraction-first reflection.** Describe the plugin gap only. Never quote session
  content, secrets, paths, identifiers, or user code.
- **L2 — Deterministic secret/PII scrubber (hard pre-post blocker).** Scan candidate issue
  text for: AWS `AKIA`/`ASIA` keys, `-----BEGIN … PRIVATE KEY-----` blocks, `ghp_` /
  `xox[bp]-` / JWTs, 12-digit account IDs, ARNs, private IPs, emails. **Any hit ⇒ do not
  post.**
- **L3 — Quarantine.** Flagged/dirty findings go to
  `~/.claude/talon-distill/_quarantine/` for manual review — never silently dropped.

**Output & dedup.** A GitHub issue on the plugin's repo, labeled `distillation`, carrying a
hidden fingerprint marker `<!-- distill-fp: <hash> -->`. Before filing, run
`gh issue list --state all` and match by fingerprint:

| Match | Action |
|-------|--------|
| none | open new issue |
| open | append recurrence note + bump count |
| closed | **reopen as regression** |

---

## 8. skill-creator handoff

skill-creator authors the `distill-plugin` SKILL.md. For `optimize_description` /
`create_skill` findings, the issue **recommends** a skill-creator pass and, where possible,
harvests the real failing prompts from the trajectory into `evals/evals.json`, so
description precision/recall can be optimized against actual misses (skill-creator's
`run_loop.py`).

---

## 9. Manual path

The `distill-plugin` skill is the **same Phase B pipeline** invoked on demand — against the
current queue, or a named plugin — for maintainers who prefer to run distillation
explicitly rather than wait for the threshold.

---

## 10. Open considerations / risks

- **Headless spawn cost/permissions.** Auto-running `claude -p` from a hook needs a
  bounded, non-interactive invocation; if unavailable, degrade gracefully to deferred
  manual runs.
- **Threshold tuning (N, K).** Start conservative to keep the public Issues tab quiet;
  revisit once we have real recurrence data.
- **Transcript schema drift.** Capture parsing depends on the transcript JSONL shape;
  keep the parser tolerant and version-aware.
- **Fault-classification precision.** The skill-vs-agent-vs-environment call is the main
  noise control; lean on `skip`.

---

## 11. Post-implementation changes (delta vs this design)

The implementation matches this design; the items below were added during build, review,
and eval, and supersede the corresponding parts above.

**Packaging.** `plugin.json` carries **no** `hooks` key — Claude Code auto-loads
`hooks/hooks.json` by convention (matches the `superpowers` plugin); the hook command is
`async`. The `talon-onboarding`→`talon-plugin-manager` rename is a v2.0.0 bump across both
catalogs/manifests; `onboard-plugin` keeps its name.

**Phase B orchestration (§2).** The reasoning steps live in the `distill-plugin` SKILL.md,
backed by deterministic CLIs in `distill/`. A **work-packet CLI** (`distill_pass.py packet`)
returns ready plugins with resolved repo, `domain_declared`, and pre-built trajectories in
one call, so the skill doesn't hand-orchestrate per record; `distill_pass.py close` marks
processed + compacts + clears the ready marker.

**Under-trigger for undeclared plugins (§5).** `load_domain_map` falls back to a cached
LLM-inferred map at `~/.claude/talon-distill/inferred/<plugin>.json`; the pass writes one
when `domain_declared` is false (a shipped `distill.json` always wins). `onboard-plugin`
offers to capture a `distill.json` at onboarding. Glob matching is version-independent
(no Python-3.13 `PurePath.full_match` dependency).

**Repo resolution.** 3-tier: (1) recorded at capture time on the evidence record, (2)
registry install-path manifest, (3) reverse-lookup via the skills that fired
(`<plugin>:<skill>` → the installed plugin providing that skill) — survives renames.

**Redaction (§7).** Added a deterministic **denylist** (`~/.claude/talon-distill/denylist.txt`)
for proprietary terms (internal hostnames, org/customer names) the shape-based scrubber
can't know; wired into the emit gate. L1 abstraction is documented as load-bearing.

**State (§6).** `compact_processed` bounds the append-only store (drops processed records).

**Dry-run & the auto-pass (§6, §10 "Headless spawn").** `TALON_DISTILL_DRY_RUN=1` makes
`emit.py` log intended `gh` calls instead of executing them (network-safe). The
`SessionEnd` auto-pass uses this as its **default**: it spawns `claude -p` with a **scoped
`--allowedTools`** list (enough to run the pipeline; `gh` is reached transitively via
`python3 emit.py`, so no global `gh` grant), drafts + redacts, and **logs** intended issues
to `~/.claude/talon-distill/pending/<plugin>.log` rather than auto-posting. Real auto-posting
is opt-in via `TALON_DISTILL_AUTOPOST=1`. A recursion guard (`TALON_DISTILL_CHILD=1`) stops
the child session from re-capturing. See `skills/distill-plugin/references/auto-pass-setup.md`.

**Triggering (§8).** The `distill-plugin` description was run through skill-creator's
`run_loop` (20 queries, 13/7 train/test). No rewrite beat the original on held-out test, so
a safer/clearer iteration was adopted; the durable finding is that this niche maintainer
skill under-triggers on natural phrasings regardless of wording — explicit invocation and
the auto-pass (explicit prompt) are the reliable trigger paths.

**Validation.** Deterministic helpers are unit-tested (85 tests). Agent-level evals
(`skills/distill-plugin/evals/`) exercise usage-friction, secret-safety (incl. a
plugin-fault + secret-in-trajectory case that reaches the emit gate), and under-trigger
inference, all in dry-run.

### Still open
- **G3 — Bash-script usage detection.** `detect_usage` is `Skill`-call-only; a plugin whose
  surface is a bundled Bash script isn't counted as "used."
- **Threshold tuning (N, K).** Still defaulted conservative; the `≥K`-recurrence trigger is
  not implemented (N-session only).
