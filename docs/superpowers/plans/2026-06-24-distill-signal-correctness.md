# Distill Signal-Correctness Increment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make distill's Phase A capture attribute friction to the right plugin, never double-record a session, and stop being silent — so every downstream Phase B decision rests on a trustworthy signal.

**Architecture:** Three independent fixes to the deterministic (no-LLM) capture layer. (#1) A new `windows.py` computes friction per-plugin over the tool-call window each plugin "owns," using a `seq` index added to the transcript parser. (#2) `evidence.py` gains an idempotent `upsert_evidence` keyed on `(session_id, plugin)`, and the recurrence/packet readers dedupe. (#3) Capture writes a one-line audit log, the hook stops discarding stderr, and `distill_pass.py` gains a `status` subcommand.

**Tech Stack:** Python 3 (stdlib only), `unittest` test classes run via `pytest`, POSIX `sh` for the hook.

## Global Constraints

- **Python 3, stdlib only.** No new dependencies. No 3.13-only features (e.g. `PurePath.full_match`) — the existing `_glob_to_regex` exists precisely to avoid that.
- **Evidence record schema unchanged.** `EvidenceRecord` fields stay as-is. No migration.
- **`scan_friction(calls, user_texts)` signature and behavior unchanged.** It keeps operating on already-sliced lists; only its *inputs* are scoped.
- **`ParsedTranscript.user_texts: list[str]` unchanged** (existing callers/tests depend on it). New fields are additive.
- **Phase B reasoning, decision taxonomy, and the redaction/emit gate are untouched.**
- **All work happens in** `plugins/talon-plugin-manager/distill/` **and** `plugins/talon-plugin-manager/skills/distill-plugin/SKILL.md`.
- **Run tests from the distill dir** (`plugins/talon-plugin-manager/distill/`) — modules use bare imports (`from transcript import ...`), so cwd must be that directory. Commands below assume it.
- **Each task ends with a commit.**

---

### Task 1: Transcript sequence index

Add a monotonic `seq` to every parsed event so friction can be windowed by proximity. Tool calls and user texts share one increasing counter in document order.

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/transcript.py`
- Test: `plugins/talon-plugin-manager/distill/test_transcript.py`

**Interfaces:**
- Produces: `ToolCall.seq: int` (defaults `-1`); `ParsedTranscript.user_events: list[tuple[int, str]]` — `(seq, text)` pairs parallel to `user_texts`.

- [ ] **Step 1: Write the failing test**

Add to `test_transcript.py`:

```python
import json, os, tempfile
from transcript import parse_transcript


def test_seq_interleaves_tool_calls_and_user_texts():
    rows = [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "user", "message": {"role": "user",
            "content": [{"type": "text", "text": "thanks"}]}},
    ]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.jsonl")
        with open(p, "w") as fh:
            for o in rows:
                fh.write(json.dumps(o) + "\n")
        parsed = parse_transcript(p)
    assert parsed.tool_calls[0].seq == 1
    assert parsed.user_events == [(0, "hi"), (2, "thanks")]
    assert parsed.user_texts == ["hi", "thanks"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_transcript.py::test_seq_interleaves_tool_calls_and_user_texts -v`
Expected: FAIL — `AttributeError: 'ToolCall' object has no attribute 'seq'` (or `ParsedTranscript` has no `user_events`).

- [ ] **Step 3: Write minimal implementation**

In `transcript.py`, add `seq` to `ToolCall` and `user_events` to `ParsedTranscript`:

```python
@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    is_error: bool = False
    result_text: str = ""
    seq: int = -1


@dataclass
class ParsedTranscript:
    tool_calls: list[ToolCall] = field(default_factory=list)
    user_texts: list[str] = field(default_factory=list)
    user_events: list[tuple[int, str]] = field(default_factory=list)
```

Then thread a counter through `parse_transcript`. Initialize `seq = 0` right after `by_id: dict[str, ToolCall] = {}`, and update the block handling:

```python
                if btype == "tool_use":
                    call = ToolCall(id=b.get("id", ""), name=b.get("name", ""),
                                    input=b.get("input") or {}, seq=seq)
                    seq += 1
                    out.tool_calls.append(call)
                    if call.id:
                        by_id[call.id] = call
                elif btype == "tool_result":
                    call = by_id.get(b.get("tool_use_id", ""))
                    if call is not None:
                        call.is_error = bool(b.get("is_error", False))
                        call.result_text = str(b.get("content", ""))[:_CLIP]
                elif btype == "text" and role == "user":
                    text = (b.get("text") or "").strip()
                    if text:
                        out.user_texts.append(text)
                        out.user_events.append((seq, text))
                        seq += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_transcript.py -v`
Expected: PASS (new test + all pre-existing transcript tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/transcript.py plugins/talon-plugin-manager/distill/test_transcript.py
git commit -m "feat(distill): add per-event seq index to the transcript parser"
```

---

### Task 2: Domain-match seqs helper

`under_triggered` returns a plugin *set* but not *which* calls matched. Add a helper that returns the `seq`s of the matching calls, so under-trigger windows can be located.

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/detect.py`
- Test: `plugins/talon-plugin-manager/distill/test_detect.py`

**Interfaces:**
- Consumes: `ToolCall.seq` (Task 1).
- Produces: `detect.domain_match_seqs(calls: list[ToolCall], sig: dict) -> list[int]` where `sig` is `{"globs": [...], "cmds": [...]}` (the shape `load_domain_map` produces).

- [ ] **Step 1: Write the failing test**

Add to `test_detect.py`:

```python
from transcript import ToolCall
from detect import domain_match_seqs


def test_domain_match_seqs_returns_matching_call_seqs():
    calls = [
        ToolCall("a", "Write", {"file_path": "infra/main.tf"}, seq=0),
        ToolCall("b", "Bash", {"command": "terraform init"}, seq=1),
        ToolCall("c", "Bash", {"command": "ls -la"}, seq=2),
        ToolCall("d", "Read", {"file_path": "README.md"}, seq=3),
    ]
    sig = {"globs": ["**/*.tf"], "cmds": ["terraform", "tofu"]}
    assert domain_match_seqs(calls, sig) == [0, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_detect.py::test_domain_match_seqs_returns_matching_call_seqs -v`
Expected: FAIL — `ImportError: cannot import name 'domain_match_seqs'`.

- [ ] **Step 3: Write minimal implementation**

In `detect.py`, add after `detect_domain`:

```python
def domain_match_seqs(calls: list[ToolCall], sig: dict) -> list[int]:
    """Seqs of the calls that match a plugin's domain signal (file globs or CLI cmds).
    Used to locate the span of under-trigger domain activity within a session."""
    globs = sig.get("globs", [])
    cmds = sig.get("cmds", [])
    out: list[int] = []
    for c in calls:
        hit = False
        if c.name in _PATH_TOOLS:
            p = c.input.get("file_path") or c.input.get("notebook_path")
            if p and any(_glob_match(str(p), g) for g in globs):
                hit = True
        if not hit and c.name == "Bash":
            command = str(c.input.get("command", ""))
            if any(re.search(rf"\b{re.escape(cmd)}\b", command) for cmd in cmds):
                hit = True
        if hit:
            out.append(c.seq)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_detect.py -v`
Expected: PASS (new test + pre-existing detect tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/detect.py plugins/talon-plugin-manager/distill/test_detect.py
git commit -m "feat(distill): add domain_match_seqs to locate under-trigger spans"
```

---

### Task 3: Per-plugin friction windowing (`windows.py`)

The core of #1. A new module computes a friction dict per plugin over the window that plugin "owns," instead of one session-global dict.

**Files:**
- Create: `plugins/talon-plugin-manager/distill/windows.py`
- Test: `plugins/talon-plugin-manager/distill/test_windows.py`

**Interfaces:**
- Consumes: `ParsedTranscript` + `ToolCall.seq` + `ParsedTranscript.user_events` (Task 1), `domain_match_seqs` (Task 2), `scan_friction` (unchanged).
- Produces: `windows.per_plugin_friction(parsed: ParsedTranscript, used: set[str], under: set[str], domain_map: dict[str, dict]) -> dict[str, dict]` — maps each plugin in `used | under` to its `friction.as_dict()`.

**Window rule (from the spec):**
- `usage(plugin)`: starts at the first `Skill` call named `<plugin>:*`; ends at the earliest of — the next `Skill` call (any plugin), the start of *another* plugin's under-trigger domain span, or end of session.
- `under_trigger(plugin)`: the inclusive `[first, last]` span of that plugin's domain-matching calls.
- `used` and `under` are disjoint (`under_triggered = detect_domain − detect_usage`), so no plugin gets both windows.

- [ ] **Step 1: Write the failing test**

Create `test_windows.py`:

```python
import unittest
from transcript import ParsedTranscript, ToolCall
from windows import per_plugin_friction

DOMAIN = {"terraform-module-steering": {"globs": ["**/*.tf"], "cmds": ["terraform", "tofu"]}}


class TestWindows(unittest.TestCase):
    def test_clean_usage_does_not_inherit_other_plugin_friction(self):
        calls = [
            ToolCall("s", "Skill", {"skill": "talon-plugin-manager:onboard-plugin"}, seq=0),
            ToolCall("w", "Write", {"file_path": "infra/main.tf"}, seq=1),
            ToolCall("b1", "Bash", {"command": "terraform apply"}, is_error=True, result_text="Error: boom", seq=2),
            ToolCall("b2", "Bash", {"command": "terraform apply"}, is_error=True, result_text="Error: boom", seq=4),
        ]
        parsed = ParsedTranscript(tool_calls=calls,
                                  user_texts=["no, that's wrong"],
                                  user_events=[(3, "no, that's wrong")])
        fm = per_plugin_friction(parsed, {"talon-plugin-manager"},
                                 {"terraform-module-steering"}, DOMAIN)
        # usage window = [0,1): only the Skill call -> clean
        self.assertFalse(fm["talon-plugin-manager"]["has_tool_errors"])
        self.assertEqual(fm["talon-plugin-manager"]["error_count"], 0)
        self.assertFalse(fm["talon-plugin-manager"]["correction"])
        # under-trigger window = [1,4]: 2 errors + correction text at seq 3
        self.assertTrue(fm["terraform-module-steering"]["has_tool_errors"])
        self.assertEqual(fm["terraform-module-steering"]["error_count"], 2)
        self.assertTrue(fm["terraform-module-steering"]["correction"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_windows.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'windows'`.

- [ ] **Step 3: Write minimal implementation**

Create `windows.py`:

```python
"""Attribute friction to each detected plugin over its activity window, so a plugin that
behaved cleanly no longer inherits friction caused elsewhere in the same session."""
from __future__ import annotations

from transcript import ParsedTranscript, ToolCall
from friction import scan_friction
from detect import domain_match_seqs


def _plugin_of_skill(c: ToolCall) -> str:
    return str(c.input.get("skill", "")).split(":", 1)[0]


def _under_spans(under: set[str], calls: list[ToolCall],
                 domain_map: dict[str, dict]) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for p in under:
        seqs = domain_match_seqs(calls, domain_map.get(p, {}))
        if seqs:
            spans[p] = (min(seqs), max(seqs))
    return spans


def per_plugin_friction(parsed: ParsedTranscript, used: set[str], under: set[str],
                        domain_map: dict[str, dict]) -> dict[str, dict]:
    calls = parsed.tool_calls
    skill_seqs = [c.seq for c in calls if c.name == "Skill"]
    spans = _under_spans(under, calls, domain_map)
    span_starts = [lo for (lo, _hi) in spans.values()]
    out: dict[str, dict] = {}
    for plugin in used | under:
        if plugin in used:
            start = min(c.seq for c in calls
                        if c.name == "Skill" and _plugin_of_skill(c) == plugin)
            ends = [s for s in skill_seqs if s > start] + [s for s in span_starts if s > start]
            end = min(ends) if ends else None  # None -> open to end of session
            in_window = (lambda s, lo=start, hi=end: s >= lo and (hi is None or s < hi))
        else:
            span = spans.get(plugin)
            if span is None:
                out[plugin] = scan_friction([], []).as_dict()
                continue
            in_window = (lambda s, lo=span[0], hi=span[1]: lo <= s <= hi)
        wcalls = [c for c in calls if in_window(c.seq)]
        wtexts = [t for (sq, t) in parsed.user_events if in_window(sq)]
        out[plugin] = scan_friction(wcalls, wtexts).as_dict()
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_windows.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/windows.py plugins/talon-plugin-manager/distill/test_windows.py
git commit -m "feat(distill): per-plugin friction windowing (windows.py)"
```

---

### Task 4: Wire windowing into capture (completes #1)

Replace the session-global friction call in `capture.py` with `per_plugin_friction`, add a fixture exercising the bleed, and a capture-level regression test. Existing capture tests must stay green.

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/capture.py:77-93`
- Create: `plugins/talon-plugin-manager/distill/fixtures/transcript_friction_bleed.jsonl`
- Test: `plugins/talon-plugin-manager/distill/test_capture.py`

**Interfaces:**
- Consumes: `windows.per_plugin_friction` (Task 3).

- [ ] **Step 1: Create the fixture**

Create `fixtures/transcript_friction_bleed.jsonl` (one JSON object per line):

```json
{"type":"user","message":{"role":"user","content":"onboard a plugin"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"s1","name":"Skill","input":{"skill":"talon-plugin-manager:onboard-plugin"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"s1","content":"Launching skill"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"w1","name":"Write","input":{"file_path":"infra/main.tf"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"w1","content":"written"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"b1","name":"Bash","input":{"command":"terraform apply"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"b1","content":"Error: boom","is_error":true}]}}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"no, that's wrong"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"b2","name":"Bash","input":{"command":"terraform apply"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"b2","content":"Error: boom","is_error":true}]}}
```

- [ ] **Step 2: Write the failing test**

Add to `test_capture.py` (near the other constants, add `BLEED`):

```python
BLEED = os.path.join(FIXDIR, "transcript_friction_bleed.jsonl")
```

```python
    def test_friction_is_localized_per_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"talon-plugin-manager": "",
                                    "terraform-module-steering": FIXDIR})
            payload = {"session_id": "s", "transcript_path": BLEED, "cwd": "/x",
                       "hook_event_name": "SessionEnd"}
            run_capture(payload, store, ip)
            from evidence import read_evidence
            tpm = read_evidence(store, "talon-plugin-manager")[0]["friction"]
            tms = read_evidence(store, "terraform-module-steering")[0]["friction"]
            self.assertFalse(tpm["has_tool_errors"])   # clean usage window
            self.assertEqual(tpm["error_count"], 0)
            self.assertTrue(tms["has_tool_errors"])     # errors localized to under-trigger
            self.assertEqual(tms["error_count"], 2)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest test_capture.py::TestCapture::test_friction_is_localized_per_plugin -v`
Expected: FAIL — `tpm["has_tool_errors"]` is `True` (current session-global friction stapled the terraform errors onto `talon-plugin-manager`).

- [ ] **Step 4: Write minimal implementation**

In `capture.py`, add the import near the other `from ... import` lines:

```python
from windows import per_plugin_friction
```

Replace lines `77`–`93` (the single `friction = ...` call and the `EvidenceRecord(... friction=friction ...)`):

```python
    friction_map = per_plugin_friction(parsed, used, under, domain_map)
    captured_at = datetime.now(timezone.utc).isoformat()
    wrote: list[str] = []
    for plugin in sorted(used | under):
        skills_used = sorted(s for c in parsed.tool_calls if c.name == "Skill"
                             for s in [str(c.input.get("skill", ""))]
                             if s.split(":", 1)[0] == plugin)
        rec = EvidenceRecord(
            session_id=payload.get("session_id", ""),
            plugin=plugin,
            kind="usage" if plugin in used else "under_trigger",
            skills_used=skills_used,
            friction=friction_map[plugin],
            captured_at=captured_at,
            transcript_path=payload.get("transcript_path", ""),
            repo=resolve_repo(registry.get(plugin, "")) or "",
        )
```

(The `append_evidence(...)` call and the `should_run_batch`/`mark_ready` block below it are unchanged in this task. The old `from friction import scan_friction` import becomes unused in `capture.py` — remove it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest test_capture.py -v`
Expected: PASS — new test passes AND the pre-existing `test_records_usage` still passes (its registry has only `talon-plugin-manager`, so there's no under-trigger boundary; the usage window stays open to end-of-session and still sees the failed bash → `has_tool_errors` remains `True`).

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/distill/capture.py \
        plugins/talon-plugin-manager/distill/fixtures/transcript_friction_bleed.jsonl \
        plugins/talon-plugin-manager/distill/test_capture.py
git commit -m "feat(distill): localize friction per plugin in capture (#1)"
```

---

### Task 5: Idempotent upsert + dedupe (`evidence.py`)

The core of #2. Add a `(session_id)`-keyed upsert and a pure dedupe helper. `append_evidence` is retained unchanged.

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/evidence.py`
- Test: `plugins/talon-plugin-manager/distill/test_evidence.py`

**Interfaces:**
- Produces: `evidence.upsert_evidence(store_dir: str, rec: EvidenceRecord) -> str`; `evidence.dedupe_evidence(rows: list[dict]) -> list[dict]`.
- Upsert semantics: replace an existing **unprocessed** record with the same `session_id`; **skip** (leave file untouched) if a **processed** record with that `session_id` exists; else append.
- Dedupe: one record per `session_id`, preferring a processed record, else the newest `captured_at`; order-preserving by first appearance.

- [ ] **Step 1: Write the failing tests**

Add to `test_evidence.py` (extend the import line to include the new names):

```python
from evidence import (EvidenceRecord, append_evidence, read_evidence,
                      upsert_evidence, dedupe_evidence)
```

```python
    def test_upsert_replaces_unprocessed_same_session(self):
        with tempfile.TemporaryDirectory() as d:
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", [],
                            {"has_tool_errors": False}, "2026-06-22T00:00:00Z", "/t"))
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", ["x"],
                            {"has_tool_errors": True}, "2026-06-24T00:00:00Z", "/t"))
            rows = read_evidence(d, "p")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["captured_at"], "2026-06-24T00:00:00Z")
            self.assertTrue(rows[0]["friction"]["has_tool_errors"])

    def test_upsert_keeps_distinct_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", [], {}, "t", "/t"))
            upsert_evidence(d, EvidenceRecord("s2", "p", "usage", [], {}, "t", "/t"))
            self.assertEqual(len(read_evidence(d, "p")), 2)

    def test_upsert_skips_when_already_processed(self):
        with tempfile.TemporaryDirectory() as d:
            seed = EvidenceRecord("s1", "p", "usage", [], {}, "2026-06-22T00:00:00Z", "/t")
            seed.processed = True
            append_evidence(d, seed)
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", [],
                            {"has_tool_errors": True}, "2026-06-24T00:00:00Z", "/t"))
            rows = read_evidence(d, "p")
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["processed"])
            self.assertEqual(rows[0]["captured_at"], "2026-06-22T00:00:00Z")

    def test_dedupe_prefers_processed_then_newest(self):
        rows = [
            {"session_id": "s1", "captured_at": "2026-06-22T00:00:00Z", "processed": False},
            {"session_id": "s1", "captured_at": "2026-06-24T00:00:00Z", "processed": False},
            {"session_id": "s2", "captured_at": "2026-06-20T00:00:00Z", "processed": True},
            {"session_id": "s2", "captured_at": "2026-06-21T00:00:00Z", "processed": False},
        ]
        out = dedupe_evidence(rows)
        self.assertEqual(len(out), 2)
        by = {r["session_id"]: r for r in out}
        self.assertEqual(by["s1"]["captured_at"], "2026-06-24T00:00:00Z")
        self.assertTrue(by["s2"]["processed"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_evidence.py -v`
Expected: FAIL — `ImportError: cannot import name 'upsert_evidence'`.

- [ ] **Step 3: Write minimal implementation**

In `evidence.py`, add after `read_evidence`:

```python
def dedupe_evidence(rows: list[dict]) -> list[dict]:
    """Collapse to one record per session_id: prefer a processed record, else the newest
    captured_at. Order-preserving by first appearance. Guards against pre-existing
    duplicate captures inflating recurrence counts."""
    best: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        sid = r.get("session_id", "")
        if sid not in best:
            best[sid] = r
            order.append(sid)
            continue
        cur = best[sid]
        if r.get("processed") and not cur.get("processed"):
            best[sid] = r
        elif bool(r.get("processed")) == bool(cur.get("processed")) and \
                str(r.get("captured_at", "")) >= str(cur.get("captured_at", "")):
            best[sid] = r
    return [best[s] for s in order]


def upsert_evidence(store_dir: str, rec: EvidenceRecord) -> str:
    """Idempotent write keyed on session_id: replace an existing unprocessed record for the
    same session; skip if a processed one exists (already judged — never re-judge); else
    append. Rewrites the per-plugin file atomically."""
    os.makedirs(store_dir, exist_ok=True)
    path = _store_path(store_dir, rec.plugin)
    rows = read_evidence(store_dir, rec.plugin)
    kept: list[dict] = []
    for r in rows:
        if r.get("session_id") == rec.session_id:
            if r.get("processed"):
                return path          # already judged; leave the file untouched
            continue                 # drop the stale unprocessed record
        kept.append(r)
    kept.append(asdict(rec))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for d in kept:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_evidence.py -v`
Expected: PASS (4 new + the pre-existing append/read tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/evidence.py plugins/talon-plugin-manager/distill/test_evidence.py
git commit -m "feat(distill): idempotent upsert + dedupe in the evidence store (#2)"
```

---

### Task 6: Make capture idempotent + dedupe recurrence paths (completes #2)

Switch capture to `upsert_evidence`, dedupe in the threshold counter and the work-packet builder, and fix the threshold test (which relied on the old dup-inflation behavior).

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/capture.py` (import + the `append_evidence` call)
- Modify: `plugins/talon-plugin-manager/distill/batch.py:8-9`
- Modify: `plugins/talon-plugin-manager/distill/distill_pass.py:11,51`
- Test: `plugins/talon-plugin-manager/distill/test_capture.py`

**Interfaces:**
- Consumes: `upsert_evidence`, `dedupe_evidence` (Task 5).

- [ ] **Step 1: Write the failing test + fix the threshold test**

In `test_capture.py`, add the idempotency test:

```python
    def test_capture_is_idempotent_per_session(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"talon-plugin-manager": ""})
            payload = {"session_id": "dup", "transcript_path": USAGE, "cwd": "/x",
                       "hook_event_name": "SessionEnd"}
            run_capture(payload, store, ip)
            run_capture(payload, store, ip)   # same session again (e.g. resume)
            from evidence import read_evidence
            self.assertEqual(len(read_evidence(store, "talon-plugin-manager")), 1)
```

And replace the existing `test_threshold_sets_ready_marker` body so it uses five **distinct** sessions (the old version captured the same `session_id` five times, which idempotency now collapses to one):

```python
    def test_threshold_sets_ready_marker(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"talon-plugin-manager": ""})
            for i in range(5):
                payload = {"session_id": f"s{i}", "transcript_path": USAGE, "cwd": "/x",
                           "hook_event_name": "SessionEnd"}
                run_capture(payload, store, ip, n_threshold=5)
            self.assertTrue(os.path.exists(os.path.join(store, "talon-plugin-manager.ready")))
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `python3 -m pytest test_capture.py::TestCapture::test_capture_is_idempotent_per_session -v`
Expected: FAIL — two records (current `append_evidence` appends a duplicate).

- [ ] **Step 3: Write minimal implementation**

In `capture.py`: change the import `from evidence import EVIDENCE_DIR, EvidenceRecord, append_evidence` to:

```python
from evidence import EVIDENCE_DIR, EvidenceRecord, upsert_evidence
```

and change the call `append_evidence(store_dir, rec)` to:

```python
        upsert_evidence(store_dir, rec)
```

In `batch.py`, change the import and `unprocessed_count`:

```python
from evidence import read_evidence, dedupe_evidence


def unprocessed_count(store_dir: str, plugin: str) -> int:
    return sum(1 for r in dedupe_evidence(read_evidence(store_dir, plugin))
               if not r.get("processed", False))
```

In `distill_pass.py`, change the import `from evidence import EVIDENCE_DIR, read_evidence` to:

```python
from evidence import EVIDENCE_DIR, read_evidence, dedupe_evidence
```

and in `build_packet`, change the `records = [...]` line to dedupe first:

```python
        records = [r for r in dedupe_evidence(read_evidence(store_dir, plugin))
                   if not r.get("processed", False)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_capture.py test_batch.py test_distill_pass.py -v`
Expected: PASS — idempotency test passes, threshold test passes with distinct sessions, batch/packet tests still green.

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/capture.py plugins/talon-plugin-manager/distill/batch.py \
        plugins/talon-plugin-manager/distill/distill_pass.py plugins/talon-plugin-manager/distill/test_capture.py
git commit -m "feat(distill): capture upserts; recurrence/packet readers dedupe (#2)"
```

---

### Task 7: Capture audit log + de-silence the hook (#3 part A)

Capture writes one summary line per run; the hook stops discarding stderr.

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/capture.py`
- Modify: `plugins/talon-plugin-manager/distill/capture-hook.sh`
- Test: `plugins/talon-plugin-manager/distill/test_capture.py`

**Interfaces:**
- Consumes: `unprocessed_count` (batch).

- [ ] **Step 1: Write the failing test**

Add to `test_capture.py`:

```python
    def test_capture_writes_audit_log(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"talon-plugin-manager": ""})
            payload = {"session_id": "s", "transcript_path": USAGE, "cwd": "/x",
                       "hook_event_name": "SessionEnd"}
            run_capture(payload, store, ip)
            log = os.path.join(d, "capture.log")   # sibling of the store dir
            self.assertTrue(os.path.exists(log))
            content = open(log).read()
            self.assertIn("session=s", content)
            self.assertIn("talon-plugin-manager", content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_capture.py::TestCapture::test_capture_writes_audit_log -v`
Expected: FAIL — `capture.log` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `capture.py`, extend the batch import to include `unprocessed_count`:

```python
from batch import should_run_batch, mark_ready, unprocessed_count
```

Add these helpers above `run_capture`:

```python
def _capture_log_path(store_dir: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(store_dir)), "capture.log")


def _write_capture_log(store_dir: str, session_id: str, wrote: list[str],
                       used: set[str], under: set[str]) -> None:
    try:
        line = (
            f"{datetime.now(timezone.utc).isoformat()} session={session_id or '-'} "
            f"wrote={sorted(wrote)} used={sorted(used)} under={sorted(under)} "
            f"unprocessed={{{', '.join(f'{p!r}: {unprocessed_count(store_dir, p)}' for p in sorted(wrote))}}}"
        )
        path = _capture_log_path(store_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
```

In `run_capture`, immediately before `return wrote`, add:

```python
    _write_capture_log(store_dir, payload.get("session_id", ""), wrote, used, under)
    return wrote
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_capture.py -v`
Expected: PASS.

- [ ] **Step 5: De-silence the hook**

Edit `capture-hook.sh` — hoist `LOG_DIR`/`mkdir` above the `if`, and redirect the exec's stderr. Replace lines 12–16 (`DIR=...` through the `fi`'s `exec` line) so the top reads:

```sh
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
LOG_DIR="${HOME}/.claude/talon-distill"
mkdir -p "$LOG_DIR" 2>/dev/null || true

if command -v python3 >/dev/null 2>&1; then
    exec python3 "$DIR/capture.py" 2>>"$LOG_DIR/capture-hook.err"   # keep stderr, don't discard it
fi
```

(Delete the now-duplicate `LOG_DIR=...` / `mkdir ...` lines that were below the `fi`; the `printf ... runtime.log` breadcrumb and `exit 0` stay.)

- [ ] **Step 6: Verify the hook still passes its tests**

Run: `sh -n capture-hook.sh && python3 -m pytest test_capture_hook.py -v`
Expected: syntax OK; both hook tests PASS (missing-python3 breadcrumb path and python3-present no-breadcrumb path are unaffected).

- [ ] **Step 7: Commit**

```bash
git add plugins/talon-plugin-manager/distill/capture.py plugins/talon-plugin-manager/distill/capture-hook.sh \
        plugins/talon-plugin-manager/distill/test_capture.py
git commit -m "feat(distill): capture audit log + de-silence the SessionEnd hook (#3)"
```

---

### Task 8: `status` subcommand + SKILL.md step (#3 part B)

A `status` surface answers "what's queued and why hasn't Phase B run," and the skill's preflight tells the operator to check it.

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/distill_pass.py`
- Modify: `plugins/talon-plugin-manager/skills/distill-plugin/SKILL.md`
- Test: `plugins/talon-plugin-manager/distill/test_distill_pass.py`

**Interfaces:**
- Produces: `distill_pass.status_rows(store_dir: str, n_threshold: int = 5) -> list[dict]`; `distill_pass.format_status(store_dir, n_threshold=5) -> str`; a `status` CLI subcommand.

- [ ] **Step 1: Write the failing test**

Add to `test_distill_pass.py` (use whatever imports the file already has; add `status_rows` to the `from distill_pass import ...`):

```python
import os, tempfile
from evidence import EvidenceRecord, append_evidence
from distill_pass import status_rows


def test_status_rows_report_unprocessed_and_threshold():
    with tempfile.TemporaryDirectory() as d:
        append_evidence(d, EvidenceRecord("a", "p1", "usage", [], {}, "2026-06-24T00:00:00Z", "/t"))
        append_evidence(d, EvidenceRecord("b", "p1", "usage", [], {}, "2026-06-25T00:00:00Z", "/t"))
        rows = {r["plugin"]: r for r in status_rows(d, n_threshold=2)}
        assert rows["p1"]["unprocessed"] == 2
        assert rows["p1"]["ready"] is True
        assert rows["p1"]["last_captured"] == "2026-06-25T00:00:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_distill_pass.py::test_status_rows_report_unprocessed_and_threshold -v`
Expected: FAIL — `ImportError: cannot import name 'status_rows'`.

- [ ] **Step 3: Write minimal implementation**

In `distill_pass.py`, add (the `dedupe_evidence` import was added in Task 6):

```python
def status_rows(store_dir: str, n_threshold: int = 5) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isdir(store_dir):
        return rows
    for fn in sorted(os.listdir(store_dir)):
        if not fn.endswith(".jsonl"):
            continue
        plugin = fn[: -len(".jsonl")]
        recs = dedupe_evidence(read_evidence(store_dir, plugin))
        unprocessed = [r for r in recs if not r.get("processed", False)]
        last = max((r.get("captured_at", "") for r in recs), default="")
        rows.append({
            "plugin": plugin,
            "unprocessed": len(unprocessed),
            "total": len(recs),
            "last_captured": last,
            "ready": len(unprocessed) >= n_threshold,
        })
    return rows


def format_status(store_dir: str, n_threshold: int = 5) -> str:
    rows = status_rows(store_dir, n_threshold)
    if not rows:
        return "no evidence captured yet"
    out = []
    for r in rows:
        verdict = "READY" if r["ready"] else f"waiting ({r['unprocessed']}/{n_threshold})"
        out.append(f"{r['plugin']}: {r['unprocessed']} unprocessed, "
                   f"last {r['last_captured'] or '-'} -> {verdict}")
    return "\n".join(out)
```

In `main`, add a `status` branch before the final `else`:

```python
    elif cmd == "status":
        store = rest[0] if rest else EVIDENCE_DIR
        print(format_status(store))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_distill_pass.py -v`
Expected: PASS.

- [ ] **Step 5: Add the SKILL.md preflight step**

In `skills/distill-plugin/SKILL.md`, under `## Preflight (do this first)`, add a third numbered item after the "Surface silent skips" item:

```markdown
3. **Check the queue.** Run `python3 ${CLAUDE_PLUGIN_ROOT}/distill/distill_pass.py status`.
   It lists each plugin's unprocessed evidence count, last capture time, and whether the
   batch threshold is met. If everything is below threshold, there may be nothing to
   process yet — say so rather than forcing a pass. (For the silent async hook's own
   stderr, see `~/.claude/talon-distill/capture-hook.err` and `capture.log`.)
```

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/distill/distill_pass.py \
        plugins/talon-plugin-manager/distill/test_distill_pass.py \
        plugins/talon-plugin-manager/skills/distill-plugin/SKILL.md
git commit -m "feat(distill): status subcommand + preflight queue check (#3)"
```

---

### Task 9: Full-suite + manual smoke verification gate

**Files:** none (verification only).

- [ ] **Step 1: Run the whole distill suite**

Run: `python3 -m pytest . -v`
Expected: all tests PASS (pre-existing 85 + the new tests). Note the total count.

- [ ] **Step 2: Smoke-test `status` against the real store**

Run: `python3 distill_pass.py status ~/.claude/talon-distill/evidence`
Expected: prints a line for `talon-plugin-manager` and `terraform-module-steering`. Because Task 6 dedupes, the live duplicate of session `7096aeb5` is counted **once** (each plugin shows `1 unprocessed`, not 2).

- [ ] **Step 3: Confirm idempotency against the live duplicate (read-only check)**

Run: `python3 -c "import sys; sys.path.insert(0,'.'); from evidence import read_evidence, dedupe_evidence; import os; s=os.path.expanduser('~/.claude/talon-distill/evidence'); print(len(read_evidence(s,'talon-plugin-manager')), '->', len(dedupe_evidence(read_evidence(s,'talon-plugin-manager'))))"`
Expected: prints `2 -> 1` (raw store still has the historical duplicate; dedupe collapses it). This confirms the recurrence path no longer inflates.

- [ ] **Step 4: Final commit (if any docs/notes changed); otherwise done**

No code changes expected here. If the run revealed anything needing a fix, address it in the relevant task above and re-run.

---

## Self-Review

**Spec coverage:**
- #1 friction localization → Tasks 1 (seq), 2 (domain_match_seqs), 3 (windows.py), 4 (wire + fixture + test). ✓
- #2 idempotent capture → Tasks 5 (upsert/dedupe), 6 (wire + threshold-test fix). ✓
- #3 de-silence + status → Tasks 7 (audit log + hook stderr), 8 (status + SKILL.md). ✓
- Verification gate (full pytest + manual smoke) → Task 9. ✓

**Type/name consistency:** `ToolCall.seq`, `ParsedTranscript.user_events`, `domain_match_seqs`, `per_plugin_friction`, `upsert_evidence`, `dedupe_evidence`, `status_rows`/`format_status` are defined where produced and consumed with matching signatures across tasks. `scan_friction` and `append_evidence` keep their existing signatures.

**Backward-compat:** evidence schema unchanged; `user_texts` retained; `scan_friction`/`append_evidence` retained; existing capture/evidence/hook tests kept green (the one intentional test change — `test_threshold_sets_ready_marker` → distinct sessions — is justified because the old assertion depended on the dup-inflation bug #2 fixes).
