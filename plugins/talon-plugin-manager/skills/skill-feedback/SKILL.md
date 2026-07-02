---
name: skill-feedback
description: >-
  Use IMMEDIATELY when a Talon plugin's skill was just used and the user reacted with
  dissatisfaction — they corrected or contradicted it, redid the work themselves, showed
  frustration, or abandoned the approach it steered toward — to offer filing a redacted
  enhancement issue on that plugin's own repo. Also use when the user explicitly says a Talon
  skill "isn't working", "gave bad/wrong guidance", or asks to send feedback or file an issue
  about a skill's behavior. Collects the relevant exchange, scrubs secrets/PII, writes the
  finding abstraction-first, and files it only after your approval. Default marketplace: Talon
  (falconh/talon). Not the domain task itself; not onboarding or releasing a plugin
  (onboard-plugin); not authoring or editing a skill or its description (skill-creator).
---

# File real-time feedback on a Talon skill

This skill turns a moment where a Talon plugin's skill disappointed the user into a concrete,
redacted GitHub issue on that plugin's repo — while the context is live and the user can confirm.
You reach it two ways: the `SessionStart`/`PostToolUse` directive primed you to watch for the
user's dissatisfaction and you noticed it, or the user invoked you directly ("this skill isn't
working").

All helper scripts live in `${CLAUDE_PLUGIN_ROOT}/distill/`; run them with `python3`. All state
(pending drafts, quarantine, dry-run log) lives under `$TALON_DISTILL_HOME` (default
`~/.claude/talon-distill`).

## Absolute rules

1. **Abstraction-first — this is load-bearing.** Describe the *skill's guidance gap*, never quote
   verbatim session content, secrets, file paths, identifiers, internal hostnames, or customer
   names. The scrubber only catches known secret *shapes*; only your abstraction discipline stops
   an internal hostname or a customer name from reaching a public issue.
2. **The scrubber is a hard gate.** Every issue goes through `feedback_emit.py`, which blocks and
   quarantines a secret/PII hit or a denylisted term. A `quarantined` result means stop, not retry.
3. **Judge the user's reaction, not your own output.** Trigger on observable dissatisfaction
   signals — correction, redo, frustration, abandonment. When unsure, do not nudge.

## What counts as dissatisfaction

- The user corrects or contradicts the skill-guided output.
- The user redoes the skill's work themselves or discards it.
- The user expresses frustration or disappointment.
- The user abandons the approach the skill steered toward.
- Repeated back-and-forth just to get the output acceptable.

Neutral or ambiguous outcomes are **not** triggers. A false nudge is worse than a missed one.

## Flow

1. **Identify the target.** Determine which Talon skill disappointed the user and its repo. Resolve
   the repo with:
   `python3 -c "import sys; sys.path.insert(0,'${CLAUDE_PLUGIN_ROOT}/distill'); from registry import load_talon_registry, resolve_repo; from paths import installed_plugins; r=load_talon_registry(installed_plugins()); print(resolve_repo(r.get('<plugin>','')) or '')"`
   If it prints nothing, you cannot resolve a repo — tell the user and stop (nothing to file against).

2. **First nudge (three-way).** Ask once, lightweight:
   > The `<skill>` output didn't seem to land. File an enhancement issue on `<repo>`?
   > 1. Yes, show me the draft first
   > 2. Yes, just file it
   > 3. No
   If the user already answered a nudge for this same skill this session, do not ask again.

3. **Draft the finding (abstraction-first).** Build a finding JSON:
   ```json
   {
     "repo": "<owner>/<plugin-repo>",
     "plugin": "<plugin>",
     "skill": "<plugin>:<skill>",
     "title": "[feedback] <short gap summary>",
     "body": "<abstract description of the skill's guidance gap + the concrete improvement, written so it carries no verbatim session content>",
     "labels": ["distill-feedback"]
   }
   ```
   - On choice **1**, show the user the title/body first; apply any edits they give.
   - On choice **2**, skip showing the draft (but you still scrub — see step 4).

4. **File it.** Write the finding to a temp file and run:
   `python3 ${CLAUDE_PLUGIN_ROOT}/distill/feedback_emit.py --finding-file <finding.json>`
   Read the printed status:
   - `opened` → issue filed; give the user the URL.
   - `quarantined` → the scrubber found a secret/PII/denylisted term. **Stop.** Tell the user it
     needs manual review; do not re-post. If you were on the fast path (choice 2), this is where
     you fall back to showing them a more abstract rewrite.
   - `deferred` → no `gh`/token available; the redacted draft is queued in
     `$TALON_DISTILL_HOME/pending/`. Tell the user it's queued (or post via GitHub MCP if available,
     never a body that hasn't passed `feedback_emit.py`).
   - To rehearse without posting, set `TALON_DISTILL_DRY_RUN=1` (calls are logged, not run).
