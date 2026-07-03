# Real-Time Skill Feedback — Agent-Judged Issue Filing — Design

**Status:** Draft (design phase) · **Date:** 2026-07-02 · **Owner:** falconh
**Base:** `origin/master` @ `da48919` · **Branch:** `design/realtime-skill-feedback`
**Touches:** create `plugins/talon-plugin-manager/skills/skill-feedback/SKILL.md` and its hook
scripts; rewrite `plugins/talon-plugin-manager/hooks/hooks.json`; **retire** the batched distill
subsystem (`distill/{capture,capture-hook.sh,evidence,batch,windows,detect,transcript,trajectory,distill_pass,pass_state,fingerprint}.py`
and `skills/distill-plugin/`); **retain and reuse** the safety spine
(`distill/{emit,redact,issues,registry,paths}.py`).

## Problem & Goal

The shipped distill pipeline turns real plugin usage into filed improvement issues, but it does so
on a **batched, deferred** model: a deterministic `SessionEnd` hook records evidence, a threshold
marks a plugin "ready," and a separate reflective pass (run later, by hand) reasons over the batch
and files issues. Two properties of that model are unsatisfying for the maintainer:

1. **The signal that matters most — whether the user was dissatisfied with a skill's output — is
   inferred, not observed.** Phase A approximates it with deterministic friction regexes
   (`"no, that's wrong"`, `"still broken"`), and Phase B reasons about it later from a rendered
   trajectory, with the user long gone. Dissatisfaction is a **judgment** signal; static keyword
   matching has poor recall (a user who quietly redoes the work, rephrases, or goes terse expresses
   real dissatisfaction with no trigger words), and after-the-fact reasoning loses the live context.
2. **Findings surface late.** Evidence accumulates against an N-session threshold that rarely trips
   at a real ~1-session-per-few-days cadence, so a genuine "that skill missed" moment may never be
   acted on while it is fresh.

**Goal:** replace the batched capture→file architecture with a **real-time, agent-judged** flow. The
moment a Talon skill's output disappoints the user, the agent — which has the full conversation, the
actual output, and the user's reaction — detects it, and offers to file a redacted enhancement issue
on that plugin's repo. This fully uses the LLM's judgment where a static script cannot, and closes
the loop while the context is live.

## Design decisions (locked in brainstorming)

| Decision | Choice | Rationale |
| --- | --- | --- |
| **Trigger timing** | Real-time, per-turn (in-session) | Act while context is live and a user is present to approve. |
| **Judge** | **Agent-native** (Approach B), not an independent judge | Sentiment toward output is judgment-based; the agent has the richest context. An independent judge gated behind a keyword pre-check would rarely be woken on non-keyword dissatisfaction — the exact case that matters. |
| **Judge framing** | **Observational**, not self-evaluative | Instruct the agent to detect the *user's* dissatisfaction signals (an external fact), never to grade its own output quality. This neutralizes self-grading bias, which only threatened the narrower attribution step — itself corrected by the human approval gate. |
| **Data form** | Abstract gap description **+ scrubbed excerpts**, human-approved | Public repo (`falconh/talon`) — excerpts must pass the secret/PII scrubber; the human confirms. |
| **Approval UX** | Nudge-first, three-way | Cheap first touch; user picks review depth. |
| **Scope vs. distill** | **Full replacement**; drop under-trigger | One simple real-time system. A post-execution judge structurally cannot see "no skill fired at all," and that case is dropped by choice. The scrubber/redaction/issue spine is retained. |
| **Dedup** | **None** (no fingerprint dedup) | Reliably fingerprinting a "gap" is ambiguous — it risks over-merging distinct issues and missing true dupes. The human approving every file already serves as dedup. |

## Scope

**In scope:**
- A **standing directive** that primes the agent to self-monitor for user dissatisfaction after any
  Talon skill runs, kept salient across a long session.
- A **`skill-feedback` skill** the agent invokes on a detection, owning: identify skill + repo,
  gather the relevant exchange, scrub, draft, nudge, approve, file.
- **Retire** the batched pipeline; **reuse** the scrubber/redaction/issue-filing spine.
- A **manual backstop**: the user can invoke `skill-feedback` directly at any time.

**Non-goals:**
- **Under-trigger detection** ("a skill should have fired but didn't"). Dropped with the batched
  pipeline; structurally invisible to a post-execution judge.
- **Cross-session dedup / recurrence counting.** Removed with fingerprinting.
- **Auto-posting without approval.** Every file is human-gated (an env flag may enable dry-run for
  evals only).

## Architecture & components

Three pieces, plus a reused spine.

1. **Standing directive (the trigger).**
   - A **`SessionStart`** hook injects a short, always-on instruction priming the agent to watch for
     the user's dissatisfaction signals after Talon skill use.
   - A **`PostToolUse`** hook matching the `Skill` tool re-asserts a focused reminder *at the moment*
     a Talon-registry plugin's skill is invoked ("you just used `<plugin>:<skill>` — watch the next
     reactions"). Event-driven re-assertion keeps the directive salient without periodic spam, and
     addresses Approach B's main risk (instruction fade in long contexts).
   - Both hooks are thin scripts that emit `additionalContext`; the `PostToolUse` script inspects the
     tool input and only fires for skills whose plugin resolves in the Talon registry.

2. **`skill-feedback` skill (the workflow).** Agent-triggered once dissatisfaction is detected (or
   invoked manually). It owns the full flow: identify the target skill and its repo (via the
   registry), gather the relevant exchange from live context, run excerpts through the scrubber,
   draft an abstract gap description + scrubbed excerpts, deliver the three-way nudge, and file via
   the reused emit path. A recursion guard prevents the feedback flow from monitoring itself.

3. **Scrubber / emit spine (reused, unchanged).** `redact.py` (secret/PII scrub), the denylist,
   `emit.py` (hard gate + quarantine), `issues.py` (`gh issue create`), `registry.py`/`paths.py`.
   The safety gate carries over exactly; `emit.py` blocking/quarantining is authoritative.

### Data flow

```
Talon skill used
  └─ PostToolUse hook re-asserts the watch directive
       └─ agent observes the user's subsequent reactions
            └─ detects dissatisfaction (observational signals)
                 └─ invokes skill-feedback
                      ├─ resolve target skill + repo (registry); no repo ⇒ no nudge
                      ├─ gather relevant exchange (from live context)
                      └─ THREE-WAY NUDGE:
                           1) "show draft first" → draft → scrub → show → approve/edit → emit
                           2) "just file it"     → draft → scrub → emit        (skip review)
                           3) "no"               → drop; suppress re-nudge for this skill this session
                                 └─ emit: scrub gate → gh issue create (or pending queue if gh absent)
```

Manual backstop: the user invokes `skill-feedback` directly (covers a missed auto-detection).

## Detection criteria (the directive)

The agent watches, after a Talon skill runs, for signals that **the user** was dissatisfied with its
result:
- corrects or contradicts the skill-guided output ("no, that's not what I meant", "that's wrong");
- redoes the skill's work themselves or discards what it produced;
- expresses frustration or disappointment;
- abandons the approach the skill steered toward;
- repeated back-and-forth just to get the output acceptable.

**Not** triggers: the agent second-guessing its own quality with no negative reaction from the user;
neutral or ambiguous outcomes. When unsure, **do not nudge** — false nudges are how this becomes
nagware, so the bias is against interrupting.

## The nudge / approval flow

On a detection, the agent asks **once**, lightweight:

> The `<skill>` output didn't seem to land. File an enhancement issue on `<plugin-repo>`?
> 1. **Yes, show me the draft first** → draft → scrub → show title/body/scrubbed excerpts → approve or edit → file.
> 2. **Yes, just file it** → draft → scrub → file directly. *(Skips the review, not the redaction — the scrubber still gates it.)*
> 3. **No** → drop it; do not re-nudge about this **same skill** for the rest of the session.

The in-session fatigue guard keys on the **skill name** (not a fingerprint): once the user has
answered a nudge for a given skill, that skill is not re-nudged this session.

## Error & edge handling

- **Scrubber quarantine (secret/PII/denylist hit).** A block means *stop, not retry*. On the review
  path (option 1) the agent surfaces the tripped category and offers a more abstract rewrite. On the
  fast path (option 2) a hit **degrades to the review path** — never files, never silently drops. The
  fast path can never become a leak path.
- **Final-content scrubbing.** The scrubber runs on the *final* filed text — including any user edits
  on option 1 — so an edit cannot reintroduce a secret past the gate.
- **No `gh` / not authenticated / offline.** Cannot file → the drafted finding is written to a pending
  location and the user is told it is queued; the finding is never lost.
- **Repo resolution / scope.** The target repo comes from the Talon plugin registry. If the skill is
  not a registry plugin or its repo cannot be resolved, the agent does not nudge — there is nothing
  to file against. Scope is installed Talon plugins only.
- **False positives.** Contained by design: bias-to-not-nudge, one nudge per skill per session, and a
  "No" suppressing repeats. A wrong nudge costs one "no" and leaves nothing behind.
- **Directive salience (Approach B's main risk).** Re-asserted by the `PostToolUse` hook at each
  Talon skill use; the manual backstop covers any miss.
- **Recursion guard.** The `skill-feedback` invocation is not itself a monitored "skill output" — a
  `CHILD`-style guard (mirroring the retired capture recursion guard) prevents the feedback flow from
  triggering feedback about itself.
- **Dry-run / test mode.** Reuse the existing `TALON_DISTILL_DRY_RUN` env flag so evals log the
  intended `gh` call instead of posting — the whole flow is testable without touching the public repo.

## Testing

The system splits into a *mechanical spine* (deterministic, unit-testable) and a *judgment layer*
(agent detection, not unit-testable), so it needs two kinds of testing.

**Deterministic unit tests** (carry over / extend the existing suite):
- Scrubber/emit gate: secret, PII, and denylist hits block and quarantine; clean input passes.
- Final-content scrubbing: an edited draft with a planted secret is still caught.
- Repo resolution from the registry; a non-registry skill yields no target and no nudge.
- Pending-queue fallback when `gh` is absent.
- Recursion guard: the feedback flow does not feed back on itself.
- Three-way nudge → action mapping: choices 1 / 2 / 3 drive show-draft / file-direct / drop.
- Hook scripts: `SessionStart` inject and `PostToolUse` re-assert fire (and the latter only for
  Talon-registry skills).

**Judgment-layer evals** (the skill-creator matrix; sandboxed with a fake-`gh` PATH shim +
`TALON_DISTILL_DRY_RUN`):
- **Recall (the whole point of Approach B):** a transcript where the user is dissatisfied *without*
  trigger keywords ("let me just do this myself", terse rephrasing) → detection + nudge still fire.
- **Precision / no nagware:** a neutral, satisfied control transcript → **no** nudge, **no** issue.
- Keyword-explicit dissatisfaction → nudge + (on approval) a scrubbed issue in the dry-run log, with
  no secret/hostname in the body.
- Secret in the exchange → scrubbed or quarantined, never in the filed body.
- Option 2 ("just file") → files without showing a draft, still scrubbed.

The eval matrix is how detection quality is actually judged, since precision/recall on sentiment is
exactly what unit tests cannot capture.

## Migration / retirement

- Remove the `SessionEnd` capture hook and the batched modules listed in **Touches**.
- Remove the `distill-plugin` processing skill; `skill-feedback` supersedes it.
- The existing evidence store under `$TALON_DISTILL_HOME` is abandoned (no migration — it holds only
  deterministic capture records the new model does not use). `paths.py` is retained for the pending
  queue / dry-run log locations.
- `emit.py` / `issues.py` are retained but may need a **minor edit to drop the fingerprint marker**
  they currently write for dedup (dedup is removed); their scrub-gate/quarantine/file behavior is
  otherwise unchanged.
- This is a **minor** version bump at least (new capability, changed behavior); the retirement of a
  shipped subsystem may argue for **major**. Decide at release per `onboard-plugin` semver rules.

## Open questions (resolve in planning)

- Exact hook payload shape for `SessionStart` vs. `PostToolUse` `additionalContext` (what Claude Code
  passes and accepts).
- Whether `skill-feedback` needs a thin `python3` entrypoint over `emit.py` or can drive it directly.
- Precise file-by-file retirement order (some retired modules may be kept transiently to avoid a
  large single deletion).
