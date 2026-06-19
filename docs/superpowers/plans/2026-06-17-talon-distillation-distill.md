# Talon Plugin Distillation — Distill Pass (Phase B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the per-plugin evidence store produced by Phase A into redacted, deduplicated GitHub issues on each plugin's repo — via a `distill-plugin` skill (the reasoning orchestrator) backed by deterministic helper scripts for trajectory rendering, secret redaction, fingerprinting, quarantine, and `gh` issue upsert — and auto-spawn that pass when a plugin's evidence crosses the batch threshold.

**Architecture:** The LLM-reasoning steps (abstraction-first reflection, the 4-way decision, skill-vs-agent-vs-environment classification) live in `skills/distill-plugin/SKILL.md`; the agent following that skill calls small, fully-tested deterministic CLIs in `distill/` for the mechanical work. A hard secret/PII scrubber gates every issue before it is posted (dirty findings are quarantined, never dropped). The Phase-A capture CLI is extended to spawn this pass headless (`claude -p`) when a `.ready` marker is set, with a recursion guard so the spawned session never re-triggers capture.

**Tech Stack:** Python 3.13 standard library only (`json`, `re`, `hashlib`, `subprocess`, `pathlib`, `dataclasses`, `unittest`). `gh` CLI (authenticated) for issue operations — invoked through an injectable runner so tests never touch the network. Claude Code skill (`SKILL.md`) for the reasoning layer.

## Global Constraints

- **Depends on Plan 1 (Capture) being implemented first.** This plan imports `transcript.py`, reads the evidence store written by `evidence.py`, consumes `.ready` markers from `batch.py`, and modifies `capture.py` — all delivered by `docs/superpowers/plans/2026-06-17-talon-distillation-capture.md`.
- **Python 3.13+, standard library only.** No pip dependencies.
- **Redaction is a hard gate, not advisory.** No issue is posted if the deterministic secret/PII scrubber finds any hit; the finding is quarantined to `~/.claude/talon-distill/_quarantine/` for manual review. Abstraction-first reflection (never quoting verbatim session content, secrets, paths, identifiers, or code) is a standing instruction in the SKILL.md.
- **`gh` is reached only through an injectable `runner`.** Default runner shells out to `gh`; tests inject a fake. No test makes a network call.
- **Issue destination:** the *used plugin's own repo*, label `distillation`, with a hidden fingerprint marker `<!-- distill-fp: <hash> -->` for dedup. Dedup uses `gh issue list --state all`; closed match ⇒ reopen as regression.
- **4-way decision only:** `improve_skill` / `optimize_description` / `create_skill` / `skip`. Bias to `skip`; only plugin-fault findings are filed.
- **Recursion guard:** the auto-spawned pass sets `TALON_DISTILL_CHILD=1`; capture no-ops when that env var is set.
- **Evidence store:** `~/.claude/talon-distill/evidence/<plugin>.jsonl`; ready markers `<plugin>.ready`; quarantine `~/.claude/talon-distill/_quarantine/`.

---

## File Structure

Added to the renamed plugin from Plan 1:

```
plugins/talon-plugin-manager/
  distill/
    trajectory.py     # NEW — deterministic session render (reuses transcript.py)
    redact.py         # NEW — L2 secret/PII scrubber (hard blocker)
    quarantine.py     # NEW — L3 quarantine writer
    fingerprint.py    # NEW — finding fingerprint + hidden marker
    issues.py         # NEW — gh issue wrapper (injectable runner)
    emit.py           # NEW — gate: scrub → quarantine|open|update|reopen (+ CLI)
    pass_state.py     # NEW — ready list / mark-processed / clear-ready (+ CLI)
    capture.py        # MODIFIED — auto-spawn + recursion guard
    test_trajectory.py test_redact.py test_quarantine.py
    test_fingerprint.py test_issues.py test_emit.py
    test_pass_state.py test_capture_spawn.py
  skills/distill-plugin/
    SKILL.md          # NEW — the reasoning orchestrator (manual + auto entry)
```

---

## Task 1: Trajectory builder (`distill/trajectory.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/trajectory.py`
- Test: `plugins/talon-plugin-manager/distill/test_trajectory.py`

**Interfaces:**
- Consumes: `transcript.parse_transcript` (Plan 1, Task 3) and the fixture `fixtures/transcript_usage.jsonl` (Plan 1, Task 3).
- Produces: `build_trajectory(transcript_path: str, clip: int = 200) -> str` — a deterministic, lossless-ish, one-line-per-tool-call render with `✓`/`✗` status. CLI: `python3 trajectory.py <transcript_path>` prints it.

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_trajectory.py`:

```python
import os
import unittest
from trajectory import build_trajectory

USAGE = os.path.join(os.path.dirname(__file__), "fixtures", "transcript_usage.jsonl")


class TestTrajectory(unittest.TestCase):
    def setUp(self):
        self.text = build_trajectory(USAGE)

    def test_includes_skill_call(self):
        self.assertIn("Skill talon-plugin-manager:onboard-plugin", self.text)

    def test_marks_success_and_failure(self):
        self.assertIn("[✓] Bash python3 validate_talon.py", self.text)
        self.assertIn("[✗] Bash terraform plan", self.text)

    def test_one_line_per_call(self):
        self.assertEqual(len(self.text.splitlines()), 3)

    def test_missing_file_is_empty_string(self):
        self.assertEqual(build_trajectory("/no/file.jsonl"), "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_trajectory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'trajectory'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/trajectory.py`:

```python
#!/usr/bin/env python3
"""Deterministic, clipped render of a session transcript for distillation reflection."""
from __future__ import annotations
import sys

from transcript import parse_transcript

_ARG_FIELD = {"Bash": "command", "Skill": "skill", "Edit": "file_path",
              "Write": "file_path", "Read": "file_path", "NotebookEdit": "notebook_path"}


def build_trajectory(transcript_path: str, clip: int = 200) -> str:
    parsed = parse_transcript(transcript_path)
    lines: list[str] = []
    for i, c in enumerate(parsed.tool_calls, 1):
        status = "✗" if c.is_error else "✓"
        arg = str(c.input.get(_ARG_FIELD.get(c.name, ""), "")).strip()
        head = f"{i}. [{status}] {c.name}" + (f" {arg}" if arg else "")
        res = (c.result_text or "").replace("\n", " ").strip()[:clip]
        lines.append(head + (f" → {res}" if res else ""))
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_trajectory(sys.argv[1]) if len(sys.argv) > 1 else "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_trajectory.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/trajectory.py plugins/talon-plugin-manager/distill/test_trajectory.py
git commit -m "feat(distill): deterministic session trajectory builder"
```

---

## Task 2: Secret/PII scrubber (`distill/redact.py`) — redaction Layer 2

**Files:**
- Create: `plugins/talon-plugin-manager/distill/redact.py`
- Test: `plugins/talon-plugin-manager/distill/test_redact.py`

**Interfaces:**
- Consumes: arbitrary candidate issue text.
- Produces:
  - `scan_secrets(text: str) -> list[tuple[str, str]]` — `(kind, match)` for every hit.
  - `is_clean(text: str) -> bool` — `True` iff `scan_secrets` is empty.

  Hard blocker: any hit means the finding must not be posted (Task 5 routes it to quarantine).

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_redact.py`:

```python
import unittest
from redact import scan_secrets, is_clean


class TestRedact(unittest.TestCase):
    def test_clean_text_passes(self):
        self.assertTrue(is_clean("The onboard-plugin skill lacked guidance on remote sources."))

    def test_aws_access_key(self):
        kinds = {k for k, _ in scan_secrets("key AKIA1234567890ABCD12 here")}
        self.assertIn("aws_access_key", kinds)

    def test_private_key_block(self):
        self.assertFalse(is_clean("-----BEGIN RSA PRIVATE KEY-----\nabc"))

    def test_github_and_slack_and_jwt(self):
        gh = "ghp_" + "a" * 36
        slack = "xoxb-123456789012-abcdEFGhijkl"
        jwt = "eyJabcdefghij.eyJklmnopqrst.signature123"
        kinds = {k for k, _ in scan_secrets(f"{gh} {slack} {jwt}")}
        self.assertSetEqual(kinds & {"github_token", "slack_token", "jwt"}, {"github_token", "slack_token", "jwt"})

    def test_account_id_arn_ip_email(self):
        text = "acct 123456789012 arn:aws:iam::123456789012:role/x ip 10.0.3.4 mail a@b.com"
        kinds = {k for k, _ in scan_secrets(text)}
        for k in ("aws_account_id", "arn", "private_ip", "email"):
            self.assertIn(k, kinds)

    def test_public_ip_not_flagged_as_private(self):
        kinds = {k for k, _ in scan_secrets("8.8.8.8")}
        self.assertNotIn("private_ip", kinds)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_redact.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'redact'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/redact.py`:

```python
"""Deterministic secret/PII scrubber — redaction Layer 2 (hard pre-post blocker)."""
from __future__ import annotations
import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b")),
    ("slack_token", re.compile(r"\bxox[bpars]-[0-9A-Za-z-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[0-9A-Za-z_-]{6,}\.eyJ[0-9A-Za-z_-]{6,}\.[0-9A-Za-z_-]{6,}\b")),
    ("aws_account_id", re.compile(r"\b\d{12}\b")),
    ("arn", re.compile(r"\barn:aws[0-9a-z-]*:[0-9a-z-]*:")),
    ("private_ip", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]


def scan_secrets(text: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text or ""):
            hits.append((kind, m.group(0)))
    return hits


def is_clean(text: str) -> bool:
    return not scan_secrets(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_redact.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/redact.py plugins/talon-plugin-manager/distill/test_redact.py
git commit -m "feat(distill): deterministic secret/PII scrubber (redaction L2)"
```

---

## Task 3: Quarantine writer (`distill/quarantine.py`) — redaction Layer 3

**Files:**
- Create: `plugins/talon-plugin-manager/distill/quarantine.py`
- Test: `plugins/talon-plugin-manager/distill/test_quarantine.py`

**Interfaces:**
- Consumes: a finding dict + a reason string.
- Produces: `quarantine(finding: dict, reason: str, quarantine_dir: str = QUARANTINE_DIR) -> str` — writes a timestamped JSON file `{reason, finding}` and returns its path. `QUARANTINE_DIR` default `~/.claude/talon-distill/_quarantine`.

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_quarantine.py`:

```python
import json
import os
import tempfile
import unittest
from quarantine import quarantine


class TestQuarantine(unittest.TestCase):
    def test_writes_finding_and_reason(self):
        with tempfile.TemporaryDirectory() as d:
            path = quarantine({"plugin": "p", "title": "x"}, "secret-scan-blocked", d)
            self.assertTrue(os.path.exists(path))
            data = json.load(open(path))
            self.assertEqual(data["reason"], "secret-scan-blocked")
            self.assertEqual(data["finding"]["plugin"], "p")

    def test_creates_dir(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "q")
            path = quarantine({"plugin": "p"}, "r", sub)
            self.assertTrue(path.startswith(sub))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_quarantine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quarantine'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/quarantine.py`:

```python
"""Quarantine flagged distillation findings for manual review — redaction Layer 3."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

QUARANTINE_DIR = os.path.expanduser("~/.claude/talon-distill/_quarantine")


def quarantine(finding: dict, reason: str, quarantine_dir: str = QUARANTINE_DIR) -> str:
    os.makedirs(quarantine_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    plugin = str(finding.get("plugin", "unknown"))
    path = os.path.join(quarantine_dir, f"{ts}-{plugin}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"reason": reason, "finding": finding}, fh, ensure_ascii=False, indent=2)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_quarantine.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/quarantine.py plugins/talon-plugin-manager/distill/test_quarantine.py
git commit -m "feat(distill): quarantine writer (redaction L3)"
```

---

## Task 4: Finding fingerprint (`distill/fingerprint.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/fingerprint.py`
- Test: `plugins/talon-plugin-manager/distill/test_fingerprint.py`

**Interfaces:**
- Consumes: plugin name, decision, and a stable anchor string (the finding's normalized one-line identity).
- Produces:
  - `finding_fingerprint(plugin: str, decision: str, anchor: str) -> str` — 12-hex-char stable hash, insensitive to whitespace/case in `anchor`.
  - `marker(fp: str) -> str` → `"<!-- distill-fp: <fp> -->"`.
  - `extract_fp(body: str) -> str | None` — pulls the fingerprint back out of an issue body.

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_fingerprint.py`:

```python
import unittest
from fingerprint import finding_fingerprint, marker, extract_fp


class TestFingerprint(unittest.TestCase):
    def test_stable_across_whitespace_and_case(self):
        a = finding_fingerprint("p", "improve_skill", "Missing remote-source guidance")
        b = finding_fingerprint("p", "improve_skill", "  missing   REMOTE-source guidance ")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)

    def test_decision_changes_fingerprint(self):
        a = finding_fingerprint("p", "improve_skill", "x")
        b = finding_fingerprint("p", "optimize_description", "x")
        self.assertNotEqual(a, b)

    def test_marker_roundtrip(self):
        fp = finding_fingerprint("p", "skip", "y")
        self.assertEqual(extract_fp("body\n" + marker(fp) + "\n"), fp)

    def test_extract_none_when_absent(self):
        self.assertIsNone(extract_fp("no marker here"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_fingerprint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fingerprint'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/fingerprint.py`:

```python
"""Stable fingerprint for a distillation finding, embedded as a hidden issue marker."""
from __future__ import annotations
import hashlib
import re

_MARKER_RE = re.compile(r"<!-- distill-fp: ([0-9a-f]{12}) -->")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def finding_fingerprint(plugin: str, decision: str, anchor: str) -> str:
    raw = f"{plugin}|{decision}|{_norm(anchor)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def marker(fp: str) -> str:
    return f"<!-- distill-fp: {fp} -->"


def extract_fp(body: str) -> str | None:
    m = _MARKER_RE.search(body or "")
    return m.group(1) if m else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_fingerprint.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/fingerprint.py plugins/talon-plugin-manager/distill/test_fingerprint.py
git commit -m "feat(distill): finding fingerprint + hidden issue marker"
```

---

## Task 5: GitHub issue wrapper + emit gate (`distill/issues.py`, `distill/emit.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/issues.py`
- Create: `plugins/talon-plugin-manager/distill/emit.py`
- Test: `plugins/talon-plugin-manager/distill/test_issues.py`
- Test: `plugins/talon-plugin-manager/distill/test_emit.py`

**Interfaces:**
- `issues.py` (all take a `runner(args: list[str]) -> tuple[int, str, str]` injectable, default shells to `gh`):
  - `find_existing(repo, fp, runner) -> dict | None` — searches all states, returns the issue whose body contains `fp`.
  - `open_issue(repo, title, body, labels, runner) -> str` — returns created URL.
  - `comment(repo, number, note, runner) -> None`
  - `reopen(repo, number, runner) -> None`
- `emit.py`:
  - `emit_finding(finding: dict, runner=issues.default_runner, quarantine_dir=quarantine.QUARANTINE_DIR) -> dict` — composes Tasks 2–4 + `issues`: appends the fingerprint marker, runs the secret scrub (dirty ⇒ quarantine + `{"status":"quarantined"}`), else upserts (open / update / reopen). `finding` keys: `repo, plugin, decision, anchor, title, body, labels?, recurrence_note?`.
  - CLI: `python3 emit.py --finding-file <f.json>` prints the result dict as JSON (used by the SKILL.md).

- [ ] **Step 1: Write the failing tests**

Create `plugins/talon-plugin-manager/distill/test_issues.py`:

```python
import unittest
from issues import find_existing, open_issue


class FakeRunner:
    def __init__(self, code=0, out="", err=""):
        self.code, self.out, self.err, self.calls = code, out, err, []

    def __call__(self, args):
        self.calls.append(args)
        return self.code, self.out, self.err


class TestIssues(unittest.TestCase):
    def test_find_existing_matches_fingerprint_in_body(self):
        r = FakeRunner(out='[{"number":7,"state":"OPEN","body":"x <!-- distill-fp: abc123abc123 -->","title":"t"}]')
        found = find_existing("o/r", "abc123abc123", r)
        self.assertEqual(found["number"], 7)

    def test_find_existing_returns_none_when_no_body_match(self):
        r = FakeRunner(out='[{"number":1,"state":"OPEN","body":"unrelated","title":"t"}]')
        self.assertIsNone(find_existing("o/r", "abc123abc123", r))

    def test_open_issue_passes_labels(self):
        r = FakeRunner(out="https://github.com/o/r/issues/9\n")
        url = open_issue("o/r", "Title", "Body", ["distillation"], r)
        self.assertEqual(url, "https://github.com/o/r/issues/9")
        self.assertIn("--label", r.calls[0])
        self.assertIn("distillation", r.calls[0])
```

Create `plugins/talon-plugin-manager/distill/test_emit.py`:

```python
import json
import tempfile
import unittest
from emit import emit_finding


class FakeRunner:
    def __init__(self, list_out="[]"):
        self.list_out, self.calls = list_out, []

    def __call__(self, args):
        self.calls.append(args)
        if args[:3] == ["gh", "issue", "list"]:
            return 0, self.list_out, ""
        if args[:3] == ["gh", "issue", "create"]:
            return 0, "https://github.com/o/r/issues/1\n", ""
        return 0, "", ""


BASE = {"repo": "o/r", "plugin": "p", "decision": "improve_skill",
        "anchor": "missing remote guidance", "title": "Improve p", "body": "Clean body."}


class TestEmit(unittest.TestCase):
    def test_opens_when_no_existing(self):
        r = FakeRunner(list_out="[]")
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(BASE, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "opened")
        self.assertTrue(any(a[:3] == ["gh", "issue", "create"] for a in r.calls))

    def test_updates_when_open_exists(self):
        from fingerprint import finding_fingerprint
        fp = finding_fingerprint("p", "improve_skill", "missing remote guidance")
        r = FakeRunner(list_out=json.dumps([{"number": 5, "state": "OPEN", "body": f"<!-- distill-fp: {fp} -->", "title": "t"}]))
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(BASE, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "updated")
        self.assertTrue(any(a[:3] == ["gh", "issue", "comment"] for a in r.calls))

    def test_reopens_when_closed_exists(self):
        from fingerprint import finding_fingerprint
        fp = finding_fingerprint("p", "improve_skill", "missing remote guidance")
        r = FakeRunner(list_out=json.dumps([{"number": 6, "state": "CLOSED", "body": f"<!-- distill-fp: {fp} -->", "title": "t"}]))
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(BASE, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "reopened")
        self.assertTrue(any(a[:3] == ["gh", "issue", "reopen"] for a in r.calls))

    def test_quarantines_when_secret_present(self):
        r = FakeRunner(list_out="[]")
        dirty = {**BASE, "body": "leak AKIA1234567890ABCD12 oops"}
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(dirty, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "quarantined")
        self.assertFalse(any(a[:3] == ["gh", "issue", "create"] for a in r.calls))  # never posted
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p 'test_issues.py' -v` and `... -p 'test_emit.py' -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'issues'` / `'emit'`.

- [ ] **Step 3: Write `issues.py`**

Create `plugins/talon-plugin-manager/distill/issues.py`:

```python
"""Thin gh-CLI wrapper for distillation issues. All calls go through an injectable runner."""
from __future__ import annotations
import json
import subprocess


def default_runner(args: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def find_existing(repo: str, fp: str, runner=default_runner) -> dict | None:
    code, out, _ = runner([
        "gh", "issue", "list", "--repo", repo, "--state", "all",
        "--search", fp, "--json", "number,state,body,title", "--limit", "50",
    ])
    if code != 0:
        return None
    try:
        items = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    for it in items:
        if fp in (it.get("body") or ""):
            return it
    return None


def open_issue(repo: str, title: str, body: str, labels: list[str], runner=default_runner) -> str:
    args = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body]
    for label in labels:
        args += ["--label", label]
    code, out, _ = runner(args)
    return out.strip() if code == 0 else ""


def comment(repo: str, number: int, note: str, runner=default_runner) -> None:
    runner(["gh", "issue", "comment", str(number), "--repo", repo, "--body", note])


def reopen(repo: str, number: int, runner=default_runner) -> None:
    runner(["gh", "issue", "reopen", str(number), "--repo", repo])
```

- [ ] **Step 4: Write `emit.py`**

Create `plugins/talon-plugin-manager/distill/emit.py`:

```python
#!/usr/bin/env python3
"""Emit gate: scrub a finding, quarantine if dirty, else open/update/reopen its issue."""
from __future__ import annotations
import argparse
import json
import sys

import issues
from fingerprint import finding_fingerprint, marker
from quarantine import QUARANTINE_DIR, quarantine
from redact import scan_secrets


def emit_finding(finding: dict, runner=issues.default_runner, quarantine_dir: str = QUARANTINE_DIR) -> dict:
    repo = finding["repo"]
    fp = finding_fingerprint(finding["plugin"], finding["decision"], finding["anchor"])
    body = finding["body"].rstrip() + "\n\n" + marker(fp)
    hits = scan_secrets(finding.get("title", "") + "\n" + body)
    if hits:
        path = quarantine(
            {**finding, "fingerprint": fp, "secret_kinds": sorted({k for k, _ in hits})},
            "secret-scan-blocked", quarantine_dir,
        )
        return {"status": "quarantined", "fingerprint": fp, "path": path}

    existing = issues.find_existing(repo, fp, runner)
    labels = finding.get("labels", ["distillation"])
    note = finding.get("recurrence_note", f"Recurred (fingerprint `{fp}`).")
    if existing is None:
        url = issues.open_issue(repo, finding["title"], body, labels, runner)
        return {"status": "opened", "fingerprint": fp, "url": url}
    number = existing["number"]
    if str(existing.get("state", "")).upper() == "CLOSED":
        issues.reopen(repo, number, runner)
        issues.comment(repo, number, "Reopened as regression. " + note, runner)
        return {"status": "reopened", "fingerprint": fp, "number": number}
    issues.comment(repo, number, note, runner)
    return {"status": "updated", "fingerprint": fp, "number": number}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--finding-file", required=True)
    args = ap.parse_args()
    with open(args.finding_file, encoding="utf-8") as fh:
        finding = json.load(fh)
    print(json.dumps(emit_finding(finding)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_issues.py -v` → PASS (3).
Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_emit.py -v` → PASS (4).

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/distill/issues.py plugins/talon-plugin-manager/distill/emit.py plugins/talon-plugin-manager/distill/test_issues.py plugins/talon-plugin-manager/distill/test_emit.py
git commit -m "feat(distill): gh issue wrapper + secret-gated emit (open/update/reopen/quarantine)"
```

---

## Task 6: Pass state (`distill/pass_state.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/pass_state.py`
- Test: `plugins/talon-plugin-manager/distill/test_pass_state.py`

**Interfaces:**
- Consumes: the evidence store + `.ready` markers from Plan 1.
- Produces:
  - `ready_plugins(store_dir) -> list[str]` — plugins with a `.ready` marker.
  - `mark_processed(store_dir, plugin, session_ids) -> int` — flips `processed=True` for the named, still-unprocessed sessions; returns how many it changed.
  - `clear_ready(store_dir, plugin) -> None` — removes the marker.
  - CLI: `python3 pass_state.py list-ready <store>` | `mark-processed <store> <plugin> <s1,s2>` | `clear-ready <store> <plugin>`.

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_pass_state.py`:

```python
import os
import tempfile
import unittest
from evidence import EvidenceRecord, append_evidence, read_evidence
from batch import mark_ready
from pass_state import ready_plugins, mark_processed, clear_ready


def rec(sid):
    return EvidenceRecord(sid, "p", "usage", [], {}, "t", "/t")


class TestPassState(unittest.TestCase):
    def test_ready_plugins_lists_markers(self):
        with tempfile.TemporaryDirectory() as d:
            mark_ready(d, "p")
            mark_ready(d, "q")
            self.assertEqual(ready_plugins(d), ["p", "q"])

    def test_clear_ready_removes_marker(self):
        with tempfile.TemporaryDirectory() as d:
            mark_ready(d, "p")
            clear_ready(d, "p")
            self.assertEqual(ready_plugins(d), [])

    def test_mark_processed_flips_named_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            append_evidence(d, rec("s1"))
            append_evidence(d, rec("s2"))
            changed = mark_processed(d, "p", ["s1"])
            self.assertEqual(changed, 1)
            rows = {r["session_id"]: r["processed"] for r in read_evidence(d, "p")}
            self.assertTrue(rows["s1"])
            self.assertFalse(rows["s2"])

    def test_mark_processed_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            append_evidence(d, rec("s1"))
            mark_processed(d, "p", ["s1"])
            self.assertEqual(mark_processed(d, "p", ["s1"]), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_pass_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pass_state'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/pass_state.py`:

```python
#!/usr/bin/env python3
"""Track which evidence has been distilled and which plugins are queued for a pass."""
from __future__ import annotations
import json
import os
import sys


def ready_plugins(store_dir: str) -> list[str]:
    try:
        names = os.listdir(store_dir)
    except OSError:
        return []
    return sorted(n[:-len(".ready")] for n in names if n.endswith(".ready"))


def clear_ready(store_dir: str, plugin: str) -> None:
    try:
        os.remove(os.path.join(store_dir, f"{plugin}.ready"))
    except OSError:
        pass


def mark_processed(store_dir: str, plugin: str, session_ids: list[str]) -> int:
    path = os.path.join(store_dir, f"{plugin}.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        return 0
    sids = set(session_ids)
    changed = 0
    out: list[str] = []
    for ln in raw:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            out.append(ln)
            continue
        if r.get("session_id") in sids and not r.get("processed", False):
            r["processed"] = True
            changed += 1
        out.append(json.dumps(r, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + ("\n" if out else ""))
    return changed


def main(argv: list[str]) -> int:
    if not argv:
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "list-ready":
        print("\n".join(ready_plugins(rest[0])))
    elif cmd == "mark-processed":
        print(mark_processed(rest[0], rest[1], rest[2].split(",") if len(rest) > 2 and rest[2] else []))
    elif cmd == "clear-ready":
        clear_ready(rest[0], rest[1])
    else:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_pass_state.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/pass_state.py plugins/talon-plugin-manager/distill/test_pass_state.py
git commit -m "feat(distill): pass-state (ready list, mark-processed, clear-ready)"
```

---

## Task 7: `distill-plugin` skill (the reasoning orchestrator)

**Files:**
- Create: `plugins/talon-plugin-manager/skills/distill-plugin/SKILL.md`
- Verify: `plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py`

**Interfaces:**
- Consumes: every `distill/` helper CLI (Tasks 1–6) and the evidence store.
- Produces: a skill the agent (manual invocation or the auto-spawned `claude -p` pass) follows to convert ready evidence into redacted issues. No deterministic test — verification is the validator (frontmatter has `name` + `description`) plus a content check that the helper CLIs are referenced.

- [ ] **Step 1: Write the skill**

Create `plugins/talon-plugin-manager/skills/distill-plugin/SKILL.md`:

```markdown
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
```

- [ ] **Step 2: Verify frontmatter + references**

Run: `python3 plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py --root .`
Expected: exits `0` (the new SKILL.md has both `name` and `description`).
Run: `grep -c 'distill/' plugins/talon-plugin-manager/skills/distill-plugin/SKILL.md`
Expected: ≥ 5 (the helper CLIs are referenced).

- [ ] **Step 3: Commit**

```bash
git add plugins/talon-plugin-manager/skills/distill-plugin/SKILL.md
git commit -m "feat(distill): distill-plugin skill (reasoning orchestrator)"
```

---

## Task 8: Auto-spawn the pass + recursion guard (`distill/capture.py`)

**Files:**
- Modify: `plugins/talon-plugin-manager/distill/capture.py` (from Plan 1, Task 8)
- Test: `plugins/talon-plugin-manager/distill/test_capture_spawn.py`

**Interfaces:**
- Modifies `run_capture` to accept `spawner: callable | None = None`. When a plugin crosses the threshold and a `spawner` is given, it calls `spawner(plugin)` after setting the marker. A module-level guard makes `run_capture` return `[]` immediately when `TALON_DISTILL_CHILD=1`. `main()` wires the real `_default_spawner` (detached `claude -p` with the child env var set).
- Pre-existing Plan 1 behavior is preserved: called with no `spawner`, it never spawns (so Plan 1's `test_capture.py` still passes).

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_capture_spawn.py`:

```python
import os
import tempfile
import unittest
from capture import run_capture

HERE = os.path.dirname(__file__)
USAGE = os.path.join(HERE, "fixtures", "transcript_usage.jsonl")


def installed_with(tmp, mapping):
    import json
    p = os.path.join(tmp, "installed.json")
    plugins = {f"{n}@talon": [{"installPath": path}] for n, path in mapping.items()}
    json.dump({"version": 2, "plugins": plugins}, open(p, "w"))
    return p


class TestCaptureSpawn(unittest.TestCase):
    def _payload(self):
        return {"session_id": "s", "transcript_path": USAGE, "cwd": "/x", "hook_event_name": "SessionEnd"}

    def test_spawner_called_when_threshold_crossed(self):
        with tempfile.TemporaryDirectory() as d:
            store, ip = os.path.join(d, "store"), installed_with(d, {"talon-plugin-manager": ""})
            calls = []
            for _ in range(5):
                run_capture(self._payload(), store, ip, n_threshold=5, spawner=calls.append)
            self.assertIn("talon-plugin-manager", calls)

    def test_spawner_not_called_before_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            store, ip = os.path.join(d, "store"), installed_with(d, {"talon-plugin-manager": ""})
            calls = []
            run_capture(self._payload(), store, ip, n_threshold=5, spawner=calls.append)
            self.assertEqual(calls, [])

    def test_child_session_is_a_noop(self):
        os.environ["TALON_DISTILL_CHILD"] = "1"
        try:
            with tempfile.TemporaryDirectory() as d:
                store, ip = os.path.join(d, "store"), installed_with(d, {"talon-plugin-manager": ""})
                calls = []
                wrote = run_capture(self._payload(), store, ip, n_threshold=1, spawner=calls.append)
                self.assertEqual(wrote, [])
                self.assertEqual(calls, [])
        finally:
            del os.environ["TALON_DISTILL_CHILD"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_capture_spawn.py -v`
Expected: FAIL — `run_capture()` does not yet accept `spawner` / has no child guard (`TypeError` or assertion failure).

- [ ] **Step 3: Modify `capture.py`**

In `plugins/talon-plugin-manager/distill/capture.py`, add a default spawner and update `run_capture` + `main`. Replace the `run_capture` signature/guard and the threshold branch, and add the spawner helper:

Add near the imports:

```python
import subprocess


def _default_spawner(plugin: str) -> None:
    """Best-effort detached `claude -p` distill pass for one plugin. Never raises."""
    env = dict(os.environ)
    env["TALON_DISTILL_CHILD"] = "1"
    prompt = (
        f"Use the talon-plugin-manager distill-plugin skill to process the distillation "
        f"evidence queue for plugin '{plugin}'. Process only the ready queue, then exit."
    )
    try:
        subprocess.Popen(
            ["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except (OSError, ValueError):
        pass
```

Change the `run_capture` signature to add the guard and `spawner` param:

```python
def run_capture(payload: dict, store_dir: str, installed_plugins_path: str,
                n_threshold: int = 5, spawner=None) -> list[str]:
    if os.environ.get("TALON_DISTILL_CHILD") == "1":
        return []  # never capture inside an auto-spawned distill session (no recursion)
    registry = load_talon_registry(installed_plugins_path)
    ...
```

In the per-plugin loop, change the threshold branch to also spawn:

```python
        if should_run_batch(store_dir, plugin, n_threshold):
            mark_ready(store_dir, plugin)
            if spawner is not None:
                spawner(plugin)
```

And update `main` to pass the real spawner:

```python
    try:
        run_capture(payload, EVIDENCE_DIR, DEFAULT_INSTALLED, spawner=_default_spawner)
    except Exception:
        return 0
```

- [ ] **Step 4: Run the new test + the Plan 1 capture test (no regression)**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_capture_spawn.py -v` → PASS (3).
Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_capture.py -v` → PASS (Plan 1 tests still green).

- [ ] **Step 5: Full suite + validator**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p 'test_*.py' -v`
Expected: PASS (all Phase A + Phase B tests).
Run: `python3 plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py --root .`
Expected: exits `0`, no `ERROR:` lines.

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/distill/capture.py plugins/talon-plugin-manager/distill/test_capture_spawn.py
git commit -m "feat(distill): auto-spawn distill pass on threshold with recursion guard"
```

---

## Self-Review

**Spec coverage (Phase B sections of the design):**
- §2 Phase B — Summarize (trajectory) → Task 1; Reflect/Decide/Classify → Task 7 (SKILL.md, LLM); Redact → Tasks 2–3 + the gate in Task 5; Emit/update → Task 5. ✓
- §3 finding-type mapping (usage → improve/optimize; under-trigger → create/optimize) → Task 7 pipeline step 6. ✓
- §4 decision taxonomy (`improve_skill`/`optimize_description`/`create_skill`/`skip`) + guardrails → Task 7. ✓
- §7 redaction L1 (abstraction-first) → Task 7 absolute rules; L2 (scrubber, hard block) → Task 2 + Task 5 gate; L3 (quarantine) → Task 3 + Task 5; output dedup (fingerprint marker, `--state all`, reopen-as-regression) → Tasks 4 + 5. ✓
- §8 skill-creator handoff + harvest failing prompts into `evals/evals.json` → Task 7 decision `optimize_description`/`create_skill`. ✓
- §6 auto-spawn of the batched pass + recursion guard → Task 8. ✓

**LLM vs deterministic split (intentional):** the reflection, 4-way decision, and fault classification are reasoning steps and live in the SKILL.md (Task 7), verified structurally (validator + reference grep), not by pytest. Everything mechanical — trajectory, scrub, quarantine, fingerprint, gh upsert, pass-state, spawn — is deterministic and unit-tested (Tasks 1–6, 8).

**Placeholder scan:** every code step has complete content and an exact command + expected output; the SKILL.md is written in full. No `TBD`/"handle errors"/"write tests for the above". ✓

**Type consistency:** `emit_finding`'s `finding` keys (`repo, plugin, decision, anchor, title, body, labels?, recurrence_note?`) match the JSON the SKILL.md writes (Task 7 step 7) and the test fixtures (Task 5). `finding_fingerprint(plugin, decision, anchor)` is called identically in `emit.py` and `test_emit.py`. `ready_plugins`/`mark_processed`/`clear_ready` signatures (Task 6) match their SKILL.md CLI usage (Task 7 steps 1, 8). `run_capture(..., spawner=None)` extension (Task 8) is backward-compatible with Plan 1's `test_capture.py`. ✓

**Cross-plan dependency:** Task 1 imports `transcript.py` and Task 6/8 import `evidence.py`/`batch.py`/`capture.py` from Plan 1 — so Plan 1 must be implemented first (stated in Global Constraints).

**Known risks:** (1) the secret scrubber's broad patterns (12-digit IDs, emails) may quarantine some clean findings — acceptable, since quarantine is manual-review, not a drop, and abstraction-first keeps such tokens out of issue bodies in the first place. (2) Auto-spawning `claude -p` from a hook depends on `claude` being on PATH and authenticated; it is best-effort and wrapped so it never blocks session end, with manual `distill-plugin` invocation as the always-available fallback.

---

## Implementation Notes (delta vs plan as written)

Built as planned, with these additions/changes (the committed code reflects these):

1. **Work-packet CLI added** (`distill_pass.py`). Beyond Tasks 1–8, a `packet`/`close` CLI
   consolidates the per-record orchestration the SKILL.md (Task 7) originally hand-rolled;
   the skill now makes one `packet` call. Includes `resolve_repo` (moved to `registry.py`)
   and a skill reverse-lookup so `repo` resolves even after a rename.
2. **Under-trigger inference fallback.** `load_domain_map` reads a cached
   `~/.claude/talon-distill/inferred/<plugin>.json` when a plugin ships no `distill.json`;
   the SKILL.md writes one. Globs use a version-independent matcher (no 3.13 `full_match`).
3. **Redaction denylist** added to `redact.py`/`emit.py` (L2) for proprietary terms.
4. **Network-safe dry-run** (`TALON_DISTILL_DRY_RUN`) in `issues.py` — `gh` calls logged, not
   executed. Used for evals and as the auto-pass default.
5. **Auto-pass hardening (Task 8 / G2).** The spawn passes a scoped `--allowedTools` list and
   is **dry-run/draft-by-default**, logging intended issues to `pending/`; real posting is
   opt-in via `TALON_DISTILL_AUTOPOST=1`. `gh` is reached transitively via `python3 emit.py`,
   so no global `gh` permission is granted. Added `references/auto-pass-setup.md`.
6. **Evidence compaction** (`pass_state.compact_processed`) bounds the store; `close` calls it.
7. **Description optimized** via skill-creator `run_loop` (adopted a safer/clearer variant).
8. **Evals** (`skills/distill-plugin/evals/`) + an end-to-end pipeline test were added and run
   (unit: 85 tests; agent-level: 4 scenarios in dry-run).

Still open: **G3** (Bash-script usage detection — `detect_usage` is `Skill`-only) and the
`≥K`-recurrence batch trigger (N-session only).
