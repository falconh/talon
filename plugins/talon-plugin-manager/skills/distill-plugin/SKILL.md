---
name: distill-plugin
description: >-
  Use when the user wants to look back at how a plugin or skill actually behaved in past sessions
  and turn that reflection into filed fixes. Trigger phrases: "distill" or "process the
  session-evidence queue" for a plugin (default marketplace: Talon) and open GitHub issues for
  recurring problems; judge whether a skill helped, hurt, or gave wrong/missing/misleading guidance
  during real use and file it as an issue on the plugin's own repo; or notice that heavy domain work
  happened (e.g. many *.tf edits, terraform plan/apply) yet no skill fired, and decide whether one
  should have. Keep secrets, infra details, and account IDs out of these public issues. Use this
  whenever the ask is to grade past behavior and file what to improve — even when a specific plugin
  or skill is named (e.g. onboard-plugin, terraform-module-steering). Not the domain task itself; not
  listing or releasing a plugin (onboard-plugin); not authoring or editing a skill or its description
  (skill-creator).
---

# Distill Talon plugin usage into improvement findings

This skill closes the loop from "how a Talon plugin behaved in a real session" to "a concrete,
filed improvement." Phase A (the `SessionEnd` hook) has already captured deterministic evidence to
`~/.claude/talon-distill/evidence/<plugin>.jsonl` and dropped a `<plugin>.ready` marker when enough
accumulated. You process that queue.

All helper scripts live in `${CLAUDE_PLUGIN_ROOT}/distill/`. Run them with `python3`.

## Absolute rules

1. **Abstraction-first (redaction Layer 1) — this is load-bearing.** Describe the plugin gap only.
   NEVER quote verbatim session content, secrets, file paths, identifiers, internal hostnames,
   project/customer names, or user code in an issue. Speak about the *skill's guidance*, not the
   user's work. The downstream scrubber only catches *known secret shapes* (API keys, tokens,
   emails); it cannot recognize an internal hostname or a customer name — so if you leak one in
   prose, only your abstraction discipline stops it from going public.
2. **The scrubber is a hard gate (Layer 2/3).** Every issue goes through `emit.py`, which blocks and
   quarantines anything containing a secret/PII hit or a denylisted term
   (`~/.claude/talon-distill/denylist.txt`, e.g. your org/internal domains). Do not attempt to
   bypass it; a `quarantined` result means stop, not retry.
3. **Bias to `skip`.** Only file when the evidence shows a *plugin* problem that recurs. When in
   doubt, skip.

## Pipeline

The store dir `<STORE>` is `~/.claude/talon-distill/evidence`.

1. **Load the work packet (one call).**
   `python3 ${CLAUDE_PLUGIN_ROOT}/distill/distill_pass.py packet <STORE>`
   returns JSON with every ready plugin already resolved: its `repo`, a `domain_declared` flag,
   and a `sessions` array where each entry carries the `kind` (`usage` / `under_trigger`), the
   deterministic friction hints (`has_tool_errors`, `repeated_error_count`, `retry`, `correction`,
   `abandonment`), and a **pre-built `trajectory`**. You do not need to read the `.jsonl` files or
   render trajectories yourself — the packet is the input to your reasoning.

2. **Reflect (abstraction-first).** For each session trajectory, ask: did this plugin's skill help
   or hurt? Was its guidance missing, wrong, or misleading? For an `under_trigger` session: should
   a skill have fired for this domain activity but didn't? Write findings as abstract descriptions
   of the gap. Let the friction hints point you at where to look.

3. **Classify the fault.** For each candidate finding, decide: was the friction the **plugin's**
   fault (its guidance), the **agent's** (it ignored correct guidance), or the **environment's**
   (auth, network, unrelated tool)? Discard anything that is not the plugin's fault.

4. **Aggregate.** Group surviving findings per plugin and per gap. A gap that recurs across multiple
   sessions is stronger evidence — note the recurrence count; it sets priority and the
   `recurrence_note`.

5. **Decide (one per gap):**
   - `improve_skill` — the skill body/guidance is wrong, missing, or misleading → recommend a
     targeted edit (name the section; do not rewrite the whole skill, do not add generic
     best-practices, do not remove correct content).
   - `optimize_description` — the skill is right but under/over-triggered → recommend a
     description fix via **skill-creator**, and, where the trajectory contains a real failing
     prompt, recommend adding it to that skill's `evals/evals.json` so triggering can be tuned.
   - `create_skill` — recurring domain work no skill covers → recommend a new skill (via
     skill-creator).
   - `skip` — below the bar, or not the plugin's fault.

6. **Emit.** For each non-skip gap, write a finding JSON (`repo` comes straight from the packet) and
   post it:
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
   re-post it. If the packet's `repo` is `null`, you could not resolve the plugin's repo — skip
   emitting and note it for the user.

7. **Improve under-trigger coverage (if `domain_declared` is false).** A plugin with
   `domain_declared: false` has no domain-signal map, so Phase A can't yet detect when it *should*
   have fired. Infer its domain signals from the skill's description — the file globs and CLI
   commands that signal this plugin's territory — and cache them so future sessions catch
   under-trigger:
   ```bash
   mkdir -p ~/.claude/talon-distill/inferred
   # write ~/.claude/talon-distill/inferred/<plugin>.json
   #   {"domain_globs": ["**/*.tf"], "domain_cmds": ["terraform","tofu"]}
   ```
   Keep it tight — a few high-precision globs/commands beat broad ones that cause false
   under-trigger noise. (A plugin author can override this anytime by shipping a real `distill.json`,
   which always wins.)

8. **Close out.** After processing a plugin's queue, mark the sessions handled, compact the store,
   and clear the ready marker in one call:
   `python3 ${CLAUDE_PLUGIN_ROOT}/distill/distill_pass.py close <STORE> <plugin> <s1,s2,...>`

## When invoked automatically

The `SessionEnd` capture spawns this skill via `claude -p` with `TALON_DISTILL_CHILD=1` set, which
suppresses capture in this child session (no recursion). Process only the ready queue, then exit.
