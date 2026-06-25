# Distill — Signal-Correctness Increment — Design

**Status:** Draft (design phase) · **Date:** 2026-06-24 · **Owner:** falconh
**Base:** `origin/master` @ `b6c3249` · **Branch:** `distill-signal-correctness`
**Touches:** `plugins/talon-plugin-manager/distill/{transcript,capture,evidence,distill_pass}.py`, `distill/capture-hook.sh`, `skills/distill-plugin/SKILL.md` (`friction.py` is read but unchanged — `scan_friction` keeps its signature)

## Problem & Goal

Distill's Phase A capture has been running, but inspection of the live evidence store
(`~/.claude/talon-distill/evidence/`) shows three concrete defects that undermine the
quality and trustworthiness of every downstream Phase B decision:

1. **Friction is session-global, not per-plugin.** `capture.py` computes `scan_friction`
   once over the whole session and staples the *identical* dict onto every detected
   plugin. Observed live: session `7096aeb5` produced byte-identical friction
   (`error_count=3, repeated_error_count=2, correction=true, abandonment=true`) on both
   `talon-plugin-manager` (usage) and `terraform-module-steering` (under_trigger). A
   plugin that behaved perfectly inherits friction caused elsewhere in the session.
2. **Capture is not idempotent.** `append_evidence` blindly appends; `SessionEnd` re-fires
   (e.g. on resume). Observed live: session `7096aeb5` is recorded **twice** (captured
   `2026-06-22` and `2026-06-24`, identical content). Because the pipeline uses recurrence
   count as evidence strength, a duplicate silently fakes a "recurring" finding.
3. **The pipeline is silent and unobservable.** The `SessionEnd` hook is `async` and
   swallows output; every evidence record is `processed:false` and no issue has ever been
   filed. There is no way to answer "did capture run, and why hasn't Phase B?"

This increment fixes the **correctness and observability** of the capture layer so that
whatever Phase B eventually decides is built on a trustworthy signal. It does **not**
change the Phase B reasoning, the decision taxonomy, or the redaction gate.

## Scope

In scope (the locked increment):
- **#1** Per-plugin friction localization.
- **#2** Idempotent capture (upsert by `(session_id, plugin)`).
- **#3** De-silence the hook + a `status` surface.

Non-goals (explicitly deferred — see the parent design §11 "Still open"):
- Re-pointing distillation at claude-mem's extracted store. Rejected earlier: claude-mem
  is configured to `SKIP` `Skill`/`SlashCommand` calls (the attribution signal) and stores
  a lossy recall-oriented abstraction. The two systems share only the raw on-disk
  transcripts, not the extracted memory.
- Under-trigger precision tuning, repo-aware triggers, decoupling capture from the hook
  (P2 items #5/#6), and the claude-mem narrative auxiliary prior (#8). Revisit after this
  increment lands.
- Bash-script usage detection (G3), `≥K` recurrence trigger. Unchanged.

## Evidence (what's on disk today)

```
~/.claude/talon-distill/evidence/talon-plugin-manager.jsonl   # session 7096aeb5 ×2 (usage)
~/.claude/talon-distill/evidence/terraform-module-steering.jsonl  # session 7096aeb5 ×2 (under_trigger)
```
Both files: same `session_id`, two `captured_at` timestamps, identical `friction`, all
`processed:false`. One real session, double-recorded, never processed.

---

## #1 — Per-plugin friction localization

### Current behavior
`capture.py` (≈ line 77):
```python
friction = scan_friction(parsed.tool_calls, parsed.user_texts).as_dict()
for plugin in sorted(used | under):
    ... EvidenceRecord(..., friction=friction, ...)   # same dict for every plugin
```
`scan_friction(calls, user_texts)` derives tool-based signals from `calls`
(`has_tool_errors`, `error_count`, `repeated_error_count`, `retry`) and text-based signals
from `user_texts` (`correction`, `abandonment`).

### Design decision — parser must preserve event ordering
`ParsedTranscript` holds `tool_calls: list[ToolCall]` and `user_texts: list[str]` as **two
separate flat lists with no positional link.** Tool-based signals can be localized by
slicing the ordered `tool_calls`, but text-based signals **cannot** be windowed without
knowing where each user text sits relative to the tool calls. Localizing *only* the
tool-based signals would still leak `correction`/`abandonment` across plugins (both leaked
in the observed case).

Therefore `parse_transcript` is enriched to assign a **monotonic sequence index (`seq`)**
to every event in document order, across both tool calls and user texts, giving a single
ordered timeline to window over. This also enables the "1 soft signal + proximity" rule the
parent design (§2) always intended.

### Changes
- **`transcript.py`**
  - Add `seq: int = -1` to `ToolCall`, set to the event's position during parse.
  - Record user texts with their seq. Keep `user_texts: list[str]` as-is for backward
    compatibility (existing `scan_friction` callers/tests rely on it); add a parallel
    `user_events: list[tuple[int, str]]` (seq, text) for windowing.
  - A single incrementing counter advances on each captured tool_use **and** each captured
    user text, so seqs interleave correctly.
- **`capture.py`** — compute friction **per plugin** over that plugin's window instead of
  once per session:
  - `usage`: window = `[seq_of_first_Skill_call_named "<plugin>:*", next_different_talon_skill_seq)`
    (or end of session). Tool calls and user_events whose seq falls in the window feed
    `scan_friction`.
  - `under_trigger`: no Skill anchor exists; window = `[first_domain_match_seq,
    last_domain_match_seq]` over the calls that matched this plugin's `domain_globs`/
    `domain_cmds`, with the user_events in that span.
  - Build the windowed `list[ToolCall]` + `list[str]` (texts from the in-window
    user_events) and call the **unchanged** `scan_friction(window_calls, window_texts)`.
- **`friction.py`** — signature unchanged (`scan_friction(calls, user_texts)`); it keeps
  operating on already-sliced lists. No behavior change inside it.

### Backward-compat
Evidence record schema unchanged. `friction` dict shape unchanged. `scan_friction` public
signature unchanged. `ParsedTranscript.user_texts` unchanged (additive `user_events` +
`ToolCall.seq`). No data migration.

### Test (red-first)
New fixture transcript: `onboard-plugin`'s `Skill` call fires early and its window is clean;
later, **unrelated** tool calls raise the same error twice and a user text says "that's
wrong / give up". Assert:
- `onboard-plugin` (usage) record → `has_tool_errors == false`, `correction == false`,
  `abandonment == false`.
- the later-domain `under_trigger` record → carries the errors / text signals.
On current code both records are identical (the bug) ⇒ test is red; green after the change.

---

## #2 — Idempotent capture (upsert by `(session_id, plugin)`)

### Design — safe upsert semantics
Add `upsert_evidence(store_dir, rec)` to `evidence.py`. On write, for the target plugin's
store:
- If an **unprocessed** record with the same `(session_id, plugin)` exists → **replace** it
  with the fresh capture (latest/longest capture of a resumed session wins).
- If a **processed** record with the same key exists → **skip** (already judged; never
  resurrect, so Phase B does not re-emit an issue for a session it already closed).
- Otherwise → append.

Implementation: read existing rows, filter out the matching unprocessed key, append the new
record, rewrite the file atomically (write temp + `os.replace`). `capture.py` calls
`upsert_evidence` instead of `append_evidence`. `append_evidence` is retained (no caller
churn beyond capture) but no longer used by capture.

### Pre-existing duplicates
Add a read-time collapse in `distill_pass` (the packet/recurrence path): when loading a
plugin's evidence, dedupe to one record per `(session_id, plugin)` (prefer processed, else
newest `captured_at`) **before** counting recurrence, so the already-on-disk `7096aeb5`
duplicate doesn't inflate counts even before it is rewritten.

### Backward-compat
Schema unchanged; behavior-only change. Existing append-based tests for `append_evidence`
stay green (function retained).

### Test (red-first)
- `upsert` same `(s1, p)` twice (both unprocessed) → exactly one record.
- `upsert` `(s1, p)` then again with newer `captured_at` + more `skills_used` → one record,
  newer content.
- existing record `(s1, p)` is `processed:true`, upsert `(s1, p)` again → unchanged (skip).
- `upsert` `(s1, p)` and `(s2, p)` → two records (recurrence across real sessions preserved).

---

## #3 — De-silence the hook + `status` surface

### Change A — audit log
`capture.py` appends one line per run to `~/.claude/talon-distill/capture.log`:
```
<iso8601> session=<id> wrote=[p1,p2] used=[...] under=[...] unprocessed={p1:N,...}
```
`capture-hook.sh` redirects its own stderr to `~/.claude/talon-distill/capture-hook.err`
(append) instead of discarding it, so a crashing async hook leaves a trace.

### Change B — `status` subcommand
Add a `status` subcommand to `distill_pass.py` (alongside the existing `packet` / `close`
per parent design §11). It prints, per plugin in the evidence store:
- unprocessed record count,
- most recent `captured_at`,
- whether the batch threshold (N) is met, and if not, why Phase B hasn't auto-run.

Add a "check status first" step to `skills/distill-plugin/SKILL.md` so the manual path
starts by surfacing what's queued.

### Backward-compat
Purely additive. No schema change.

### Test (red-first)
- `status` over a seeded multi-plugin store prints expected per-plugin unprocessed counts
  and threshold verdict (assert on parsed output).
- `capture` run writes a well-formed `capture.log` line (assert format / fields).

---

## Verification gate
- `pytest` in `distill/` fully green: existing suite (85 tests) + new tests.
- Every new test demonstrated **red before green**.
- Manual smoke: run `distill_pass.py status` against the real store and confirm it reports
  the `7096aeb5` sessions; confirm the duplicate collapses to one in the recurrence count.

## Risks / open
- **Window boundaries for `under_trigger`.** Domain activity can be scattered; the
  first→last-match span may over-include. Acceptable for v1 (still far tighter than
  session-global); revisit if it over-attributes.
- **`seq` interleaving fidelity.** The parser reconstructs ordering from append order of
  tool_use/tool_result/user-text blocks; sufficient for proximity windowing, not a precise
  wall-clock timeline. Documented, not load-bearing beyond windowing.
- **Atomic rewrite contention.** `upsert_evidence` rewrites the per-plugin file; the
  `async` hook could in principle overlap. `os.replace` makes the swap atomic; last writer
  wins, which is acceptable for an append-mostly store.
