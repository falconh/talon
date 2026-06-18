---
name: distill-plugin
description: >-
  Use when distilling real session usage of Talon-marketplace plugins into improvement findings —
  processing the captured distillation evidence queue and filing redacted GitHub issues on each
  plugin's own repo. This is also the entry point the SessionEnd auto-pass invokes once a plugin's
  evidence crosses the batch threshold. Covers reviewing accumulated evidence, building deterministic
  session trajectories, reflecting (abstraction-first) on where a plugin helped or hurt, classifying
  whether friction was the plugin's, the agent's, or the environment's fault, deciding among
  improve_skill / optimize_description / create_skill / skip, redacting secrets as a hard gate, and
  opening/updating/reopening the matching issue. Not for onboarding or releasing a plugin (use
  onboard-plugin), and not for authoring a brand-new skill from scratch.
---

# Distill Talon plugin usage into improvement findings

This skill closes the loop from "how a Talon plugin behaved in a real session" to "a concrete,
filed improvement." Phase A (the `SessionEnd` hook) has already captured deterministic evidence to
`~/.claude/talon-distill/evidence/<plugin>.jsonl` and dropped a `<plugin>.ready` marker when enough
accumulated. You process that queue.

All helper scripts live in `${CLAUDE_PLUGIN_ROOT}/distill/`. Run them with `python3`.

## Absolute rules

1. **Abstraction-first (redaction Layer 1).** Describe the plugin gap only. NEVER quote verbatim
   session content, secrets, file paths, identifiers, or user code in an issue. Speak about the
   *skill's guidance*, not the user's work.
2. **The scrubber is a hard gate (Layer 2/3).** Every issue goes through `emit.py`, which blocks and
   quarantines anything containing a secret/PII hit. Do not attempt to bypass it.
3. **Bias to `skip`.** Only file when the evidence shows a *plugin* problem that recurs. When in
   doubt, skip.

## Pipeline (per ready plugin)

1. **List the queue.** `python3 ${CLAUDE_PLUGIN_ROOT}/distill/pass_state.py list-ready <STORE>`
   where `<STORE>` is `~/.claude/talon-distill/evidence`. For each ready plugin, read its
   `<plugin>.jsonl` and collect the **unprocessed** records (`processed == false`).

2. **Build trajectories.** For each unprocessed record, render the session:
   `python3 ${CLAUDE_PLUGIN_ROOT}/distill/trajectory.py <record.transcript_path>`. Read the
   friction hints already on each record (`has_tool_errors`, `repeated_error_count`, `retry`,
   `correction`, `abandonment`) — these tell you where to look.

3. **Reflect (abstraction-first).** For each trajectory, ask: did this plugin's skill help or hurt?
   Was its guidance missing, wrong, or misleading? For an `under_trigger` record: should a skill
   have fired for this domain activity but didn't? Write findings as abstract descriptions of the
   gap.

4. **Classify the fault.** For each candidate finding, decide: was the friction the **plugin's**
   fault (its guidance), the **agent's** (it ignored correct guidance), or the **environment's**
   (auth, network, unrelated tool)? Discard anything that is not the plugin's fault.

5. **Aggregate.** Group surviving findings per plugin and per gap. A gap that recurs across multiple
   sessions is stronger evidence — note the recurrence count; it sets priority and the
   `recurrence_note`.

6. **Decide (one per gap):**
   - `improve_skill` — the skill body/guidance is wrong, missing, or misleading → recommend a
     targeted edit (name the section; do not rewrite the whole skill, do not add generic
     best-practices, do not remove correct content).
   - `optimize_description` — the skill is right but under/over-triggered → recommend a
     description fix via **skill-creator**, and, where the trajectory contains a real failing
     prompt, recommend adding it to that skill's `evals/evals.json` so triggering can be tuned.
   - `create_skill` — recurring domain work no skill covers → recommend a new skill (via
     skill-creator).
   - `skip` — below the bar, or not the plugin's fault.

7. **Emit.** For each non-skip gap, write a finding JSON and post it:
   ```json
   {
     "repo": "<owner>/<plugin-repo>",
     "plugin": "<plugin>",
     "decision": "improve_skill",
     "anchor": "<stable one-line identity of the gap>",
     "title": "[distill] <short gap summary>",
     "body": "<abstract description + recommended change + recurrence count>",
     "labels": ["distillation"],
     "recurrence_note": "Seen in N sessions."
   }
   ```
   Then: `python3 ${CLAUDE_PLUGIN_ROOT}/distill/emit.py --finding-file <finding.json>`.
   Read the printed status: `opened` / `updated` / `reopened` / `quarantined`. If `quarantined`,
   tell the user a finding needs manual review (the scrubber found something) — do NOT try to
   re-post it.

8. **Close out.** After processing a plugin's queue:
   `python3 ${CLAUDE_PLUGIN_ROOT}/distill/pass_state.py mark-processed <STORE> <plugin> <s1,s2,...>`
   (the session_ids you handled), then
   `python3 ${CLAUDE_PLUGIN_ROOT}/distill/pass_state.py clear-ready <STORE> <plugin>`.

## Determining the plugin's repo

Use the plugin's manifest (`homepage`/`repository` in its `plugin.json` under the install path) to
resolve `<owner>/<plugin-repo>`. For a plugin that lives *inside* Talon (local source), the repo is
`falconh/talon` and the issue is filed there.

## When invoked automatically

The `SessionEnd` capture spawns this skill via `claude -p` with `TALON_DISTILL_CHILD=1` set, which
suppresses capture in this child session (no recursion). Process only the ready queue, then exit.
