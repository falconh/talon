# Real-Time Skill Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the batched distill capture→file pipeline with a real-time, agent-judged mechanism that, when a Talon skill's output disappoints the user, offers to file a redacted enhancement issue on that plugin's repo.

**Architecture:** A `SessionStart` hook injects a standing directive priming the agent to watch for the *user's* dissatisfaction signals; a `PostToolUse` hook re-asserts it whenever a Talon-registry skill runs. On a detection the agent invokes a new `skill-feedback` skill, which builds an abstraction-first finding, scrubs it, and files it via a new dedup-free `feedback_emit.py` after a three-way nudge (show-draft / just-file / no). The batched pipeline is retired; the scrubber/quarantine/issue-transport primitives are reused.

**Tech Stack:** Python 3 (stdlib only), POSIX `sh`, Claude Code plugin hooks + skills, `gh` CLI / GitHub REST for issue transport, `pytest` running `unittest` tests.

**Spec:** `docs/superpowers/specs/2026-07-02-realtime-skill-feedback-design.md`

## Global Constraints

- **Python 3 stdlib only.** No third-party deps. Tests are `unittest`, run via `pytest` from `plugins/talon-plugin-manager/distill/` with **bare imports** (no package prefix), matching the existing suite.
- **Public repo target `falconh/talon` — redaction is mandatory.** Every filed body passes through the scrubber (`redact.scan_secrets`); a secret/PII/denylist hit **quarantines** (stop, not retry). Findings are written abstraction-first (describe the skill gap, never quote verbatim session content).
- **No dedup.** No fingerprint, no existing-issue lookup, no marker. The human approving every file is the dedup.
- **Retire** `distill/{capture,capture-hook.sh,evidence,batch,windows,detect,transcript,trajectory,distill_pass,pass_state,fingerprint,emit,friction}.py` and `skills/distill-plugin/`. **Retain and reuse** `distill/{redact,quarantine,issues,registry,paths}.py`.
- **Env overrides (reused):** `TALON_DISTILL_HOME` (state root), `TALON_DISTILL_INSTALLED` (registry path), `TALON_DISTILL_DRY_RUN` (log intended `gh` calls, no network), `TALON_DISTILL_DRY_LOG` (dry-run log path).
- **Hooks:** `SessionStart` (directive) + `PostToolUse` matcher `"Skill"` (re-assert). The `SessionEnd` capture hook is removed.
- **Commits:** conventional-commit subjects; **every commit ends with** these two trailer lines:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01752TtFnWo8ieDbs5ba2q5i`.
- **Release is PR-only via the `onboard-plugin` skill** (Task 9) — never push to `master`; both catalogs move together.

All paths below are relative to the repo root. The distill dir is `plugins/talon-plugin-manager/distill/` (abbreviated `<D>/` in commands after a `cd`).

---

### Task 1: `feedback_emit.py` — dedup-free scrub → quarantine-or-file

The mechanical core everything files through. Composes the retained primitives; no fingerprint, no `find_existing`.

**Files:**
- Create: `plugins/talon-plugin-manager/distill/feedback_emit.py`
- Test: `plugins/talon-plugin-manager/distill/test_feedback_emit.py`

**Interfaces:**
- Consumes: `redact.scan_secrets(text, denylist)`, `quarantine.quarantine(finding, reason, quarantine_dir)`, `issues.select_backend()`, `issues.open_issue(repo, title, body, labels, runner, backend)`, `issues.default_runner`, `paths.under(*parts)`.
- Produces: `file_feedback(finding: dict, runner=issues.default_runner, quarantine_dir=QUARANTINE_DIR, denylist=None, backend=None, pending_dir=PENDING_DIR) -> dict` returning `{"status": "opened"|"quarantined"|"deferred", ...}`. Finding dict schema: `{"repo": str, "plugin": str, "skill": str, "title": str, "body": str, "labels": list[str]?}`. CLI: `python3 feedback_emit.py --finding-file <path>` prints the result JSON.

- [ ] **Step 1: Write the failing test**

```python
# plugins/talon-plugin-manager/distill/test_feedback_emit.py
"""Tests for feedback_emit.file_feedback — the dedup-free scrub→file path."""
import os
import tempfile
import unittest

import feedback_emit
import issues

CLEAN = {"repo": "falconh/talon", "plugin": "onboard-plugin", "skill": "talon-plugin-manager:onboard-plugin",
         "title": "[feedback] onboard-plugin validator path guidance unclear",
         "body": "The skill's verification step points at a path that does not resolve for a local plugin."}
DIRTY = {**CLEAN, "title": "[feedback] leak", "body": "the key AKIA1234567890ABCD00 was printed by the step"}


class TestFileFeedback(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.q = os.path.join(self.td.name, "_quarantine")
        self.pending = os.path.join(self.td.name, "pending")
        self.dry_log = os.path.join(self.td.name, "dry_run.log")
        os.environ["TALON_DISTILL_DRY_RUN"] = "1"
        os.environ["TALON_DISTILL_DRY_LOG"] = self.dry_log

    def tearDown(self):
        self.td.cleanup()
        os.environ.pop("TALON_DISTILL_DRY_RUN", None)
        os.environ.pop("TALON_DISTILL_DRY_LOG", None)

    def test_clean_finding_opens_and_logs_gh_create(self):
        res = feedback_emit.file_feedback(CLEAN, quarantine_dir=self.q, pending_dir=self.pending, denylist=[])
        self.assertEqual(res["status"], "opened")
        with open(self.dry_log, encoding="utf-8") as fh:
            log = fh.read()
        self.assertIn("gh issue create --repo falconh/talon", log)

    def test_secret_in_body_quarantines_and_does_not_file(self):
        res = feedback_emit.file_feedback(DIRTY, quarantine_dir=self.q, pending_dir=self.pending, denylist=[])
        self.assertEqual(res["status"], "quarantined")
        self.assertTrue(os.path.isdir(self.q) and os.listdir(self.q))
        self.assertFalse(os.path.exists(self.dry_log), "must not reach gh create when quarantined")

    def test_no_backend_defers_to_pending(self):
        res = feedback_emit.file_feedback(CLEAN, quarantine_dir=self.q, pending_dir=self.pending,
                                          denylist=[], backend="none")
        self.assertEqual(res["status"], "deferred")
        self.assertTrue(os.listdir(self.pending))

    def test_denylist_term_quarantines(self):
        res = feedback_emit.file_feedback(CLEAN, quarantine_dir=self.q, pending_dir=self.pending,
                                          denylist=["acme.corp"], backend="dry")
        # CLEAN has no denylist term, so it opens; now plant one:
        dirty = {**CLEAN, "body": "the step referenced db.acme.corp directly"}
        res = feedback_emit.file_feedback(dirty, quarantine_dir=self.q, pending_dir=self.pending,
                                          denylist=["acme.corp"], backend="dry")
        self.assertEqual(res["status"], "quarantined")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_emit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'feedback_emit'`.

- [ ] **Step 3: Write minimal implementation**

```python
# plugins/talon-plugin-manager/distill/feedback_emit.py
#!/usr/bin/env python3
"""Feedback emit: scrub a skill-feedback finding, quarantine if dirty, else open its issue.
No dedup — a human approves every file, so there is no fingerprint or existing-issue lookup."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys

import issues
from paths import under
from quarantine import QUARANTINE_DIR, quarantine
from redact import scan_secrets

DENYLIST_FILE = under("denylist.txt")
PENDING_DIR = under("pending")


def _load_denylist() -> list[str]:
    try:
        with open(DENYLIST_FILE, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return []


def _finding_id(finding: dict) -> str:
    """Stable local id for the pending filename (no dedup semantics)."""
    key = f"{finding.get('plugin', '')}|{finding.get('skill', '')}|{finding.get('title', '')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _defer(finding: dict, fid: str, body: str, pending_dir: str) -> str:
    os.makedirs(pending_dir, exist_ok=True)
    path = os.path.join(pending_dir, f"{fid}.md")
    labels = ",".join(finding.get("labels", ["distill-feedback"]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {finding.get('title', '')}\n\nrepo: {finding['repo']}\nlabels: {labels}\n\n{body}\n")
    return path


def file_feedback(finding: dict, runner=issues.default_runner, quarantine_dir: str = QUARANTINE_DIR,
                  denylist: list[str] | None = None, backend: str | None = None,
                  pending_dir: str = PENDING_DIR) -> dict:
    if denylist is None:
        denylist = _load_denylist()
    body = finding["body"].rstrip() + "\n"
    hits = scan_secrets(finding.get("title", "") + "\n" + body, denylist)
    if hits:
        path = quarantine({**finding, "secret_kinds": sorted({k for k, _ in hits})},
                          "secret-scan-blocked", quarantine_dir)
        return {"status": "quarantined", "path": path}
    backend = backend or issues.select_backend()
    if backend == "none":
        return {"status": "deferred", "path": _defer(finding, _finding_id(finding), body, pending_dir)}
    labels = finding.get("labels", ["distill-feedback"])
    url = issues.open_issue(finding["repo"], finding["title"], body, labels, runner, backend=backend)
    return {"status": "opened", "url": url}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--finding-file", required=True)
    args = ap.parse_args()
    with open(args.finding_file, encoding="utf-8") as fh:
        finding = json.load(fh)
    print(json.dumps(file_feedback(finding)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_emit.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/feedback_emit.py plugins/talon-plugin-manager/distill/test_feedback_emit.py
git commit -m "feat(distill): dedup-free feedback_emit scrub→quarantine-or-file path"
```

---

### Task 2: `feedback-session-start.sh` — the standing directive hook

**Files:**
- Create: `plugins/talon-plugin-manager/distill/feedback-session-start.sh`
- Test: `plugins/talon-plugin-manager/distill/test_feedback_session_start.py`

**Interfaces:**
- Produces: a POSIX `sh` script that prints the directive text to stdout (Claude Code adds a `SessionStart` hook's stdout to session context). No stdin needed; exits 0.

- [ ] **Step 1: Write the failing test**

```python
# plugins/talon-plugin-manager/distill/test_feedback_session_start.py
"""The SessionStart directive hook must emit the watch-for-dissatisfaction priming text."""
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "feedback-session-start.sh")
SH = shutil.which("sh") or "/bin/sh"


class TestSessionStartDirective(unittest.TestCase):
    def test_emits_directive(self):
        p = subprocess.run([SH, HOOK], input=b"{}", capture_output=True)
        self.assertEqual(p.returncode, 0)
        out = p.stdout.decode()
        self.assertIn("skill-feedback", out)
        self.assertIn("dissatisf", out.lower())
        self.assertIn("not", out.lower())  # "when unsure, do not interrupt"


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_session_start.py -q`
Expected: FAIL — hook file does not exist (non-zero return / FileNotFoundError).

- [ ] **Step 3: Write minimal implementation**

```sh
# plugins/talon-plugin-manager/distill/feedback-session-start.sh
#!/bin/sh
# SessionStart: prime the agent to watch for USER dissatisfaction with Talon skill output.
# Claude Code adds this hook's stdout to the session context.
cat <<'DIRECTIVE'
[talon-skill-feedback] After you use any Talon plugin skill, stay alert to whether the USER seems
dissatisfied with its result: they correct or contradict it, redo the work themselves, express
frustration, or abandon the approach it steered toward. If you observe that, invoke the
talon-plugin-manager skill-feedback skill to offer filing a redacted enhancement issue on the
plugin's repo. Judge the user's reaction, never your own output quality. When unsure, do not
interrupt — a false nudge is worse than a missed one.
DIRECTIVE
```

Then make it executable: `chmod +x plugins/talon-plugin-manager/distill/feedback-session-start.sh`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_session_start.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/feedback-session-start.sh plugins/talon-plugin-manager/distill/test_feedback_session_start.py
git commit -m "feat(distill): SessionStart directive hook priming dissatisfaction watch"
```

---

### Task 3: `feedback-post-skill.py` — the PostToolUse re-assert hook

Re-asserts the directive at the moment a Talon-registry skill runs. Silent for non-Talon skills, `skill-feedback` itself (recursion guard), and non-Skill tools.

**Files:**
- Create: `plugins/talon-plugin-manager/distill/feedback-post-skill.py`
- Test: `plugins/talon-plugin-manager/distill/test_feedback_post_skill.py`

**Interfaces:**
- Consumes: `registry.load_talon_registry(path)`, `paths.installed_plugins()`.
- Produces: `reassert_for(payload: dict, registry: dict) -> str | None` (pure; returns re-assert text or None). `main()` reads the hook payload on stdin, prints `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": <text>}}` when a re-assert applies, else nothing; always exits 0.

- [ ] **Step 1: Write the failing test**

```python
# plugins/talon-plugin-manager/distill/test_feedback_post_skill.py
"""PostToolUse re-assert fires only for Talon-registry skills, never for skill-feedback itself."""
import json
import unittest

import feedback_post_skill as h

REG = {"onboard-plugin": "/p/onboard", "talon-plugin-manager": "/p/tpm"}


class TestReassert(unittest.TestCase):
    def test_talon_skill_reasserts(self):
        note = h.reassert_for({"tool_name": "Skill",
                               "tool_input": {"skill": "onboard-plugin:onboard-plugin"}}, REG)
        self.assertIsNotNone(note)
        self.assertIn("skill-feedback", note)

    def test_skill_feedback_itself_is_silent(self):
        note = h.reassert_for({"tool_name": "Skill",
                               "tool_input": {"skill": "talon-plugin-manager:skill-feedback"}}, REG)
        self.assertIsNone(note)

    def test_non_talon_skill_is_silent(self):
        note = h.reassert_for({"tool_name": "Skill",
                               "tool_input": {"skill": "some-other:thing"}}, REG)
        self.assertIsNone(note)

    def test_non_skill_tool_is_silent(self):
        self.assertIsNone(h.reassert_for({"tool_name": "Bash", "tool_input": {"command": "ls"}}, REG))


if __name__ == "__main__":
    unittest.main()
```

Note: the module file is `feedback-post-skill.py` but Python imports need an underscore name. Import it in the test via an `importlib` shim OR name the module file with underscores and reference it with the hyphen only in `hooks.json`. **Decision:** name the file `feedback_post_skill.py` (underscores) so it is importable and testable; reference `python3 "${CLAUDE_PLUGIN_ROOT}/distill/feedback_post_skill.py"` in `hooks.json`. Update the test import accordingly (already uses `feedback_post_skill`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_post_skill.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'feedback_post_skill'`.

- [ ] **Step 3: Write minimal implementation**

```python
# plugins/talon-plugin-manager/distill/feedback_post_skill.py
#!/usr/bin/env python3
"""PostToolUse re-assert: when a Talon-registry plugin's skill is invoked, remind the agent to
watch for USER dissatisfaction. Silent for non-Talon skills, skill-feedback itself, and non-Skill
tools. Reads the hook payload on stdin, prints hook JSON on stdout. Never raises into the hook."""
from __future__ import annotations
import json
import sys

from paths import installed_plugins
from registry import load_talon_registry

REASSERT = ("[talon-skill-feedback] You just used {skill}. Watch the user's next reactions: if they "
            "correct it, redo the work themselves, show frustration, or abandon the approach, invoke "
            "the talon-plugin-manager skill-feedback skill. Judge the user's reaction, not your own "
            "output.")


def reassert_for(payload: dict, registry: dict) -> str | None:
    if payload.get("tool_name") != "Skill":
        return None
    skill = str((payload.get("tool_input") or {}).get("skill", ""))
    plugin = skill.split(":", 1)[0]
    if not plugin or plugin not in registry:
        return None
    if skill.endswith(":skill-feedback"):
        return None  # recursion guard: never monitor the feedback flow itself
    return REASSERT.format(skill=skill)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    try:
        registry = load_talon_registry(installed_plugins())
        note = reassert_for(payload, registry)
    except Exception:
        return 0
    if note:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_post_skill.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/feedback_post_skill.py plugins/talon-plugin-manager/distill/test_feedback_post_skill.py
git commit -m "feat(distill): PostToolUse re-assert hook for Talon skill dissatisfaction watch"
```

---

### Task 4: Wire `hooks/hooks.json` (remove SessionEnd capture; add SessionStart + PostToolUse)

**Files:**
- Modify: `plugins/talon-plugin-manager/hooks/hooks.json` (full rewrite)
- Test: `plugins/talon-plugin-manager/distill/test_feedback_hooks.py`

**Interfaces:**
- Consumes: the two hook scripts from Tasks 2–3.

- [ ] **Step 1: Write the failing test**

```python
# plugins/talon-plugin-manager/distill/test_feedback_hooks.py
"""hooks.json wires the feedback directive (SessionStart) + re-assert (PostToolUse), not capture."""
import json
import os
import unittest

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "hooks.json")


class TestHooksJson(unittest.TestCase):
    def setUp(self):
        with open(HOOKS, encoding="utf-8") as fh:
            self.cfg = json.load(fh)["hooks"]

    def test_no_session_end_capture(self):
        self.assertNotIn("SessionEnd", self.cfg)

    def test_session_start_runs_directive(self):
        cmd = self.cfg["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn("feedback-session-start.sh", cmd)

    def test_post_tool_use_matches_skill(self):
        entry = self.cfg["PostToolUse"][0]
        self.assertEqual(entry["matcher"], "Skill")
        self.assertIn("feedback_post_skill.py", entry["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_hooks.py -q`
Expected: FAIL — current `hooks.json` has `SessionEnd`, no `SessionStart`/`PostToolUse`.

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `plugins/talon-plugin-manager/hooks/hooks.json` with:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh \"${CLAUDE_PLUGIN_ROOT}/distill/feedback-session-start.sh\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Skill",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/distill/feedback_post_skill.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_feedback_hooks.py -q`
Expected: PASS.

- [ ] **Step 5: Manual integration verification (Claude Code wiring)**

The unit test proves the JSON is correct; this step proves Claude Code actually fires the hooks, since `PostToolUse` firing for the `Skill` tool is an assumption (spec open question).

1. Install/enable the plugin locally (`/plugin marketplace add falconh/talon` against your working copy, or a local dev install).
2. Start a new session; ask the agent to state any `[talon-skill-feedback]` guidance it received — confirms the `SessionStart` directive landed.
3. Invoke any Talon skill (e.g. `onboard-plugin`), then check whether the re-assert context appeared. To observe deterministically, temporarily prepend a debug line to `feedback_post_skill.py`'s `main()` that appends the payload to `"$TALON_DISTILL_HOME"/posttool.log`, trigger a Skill call, and confirm the log grew.
4. **If `PostToolUse` does not fire for `Skill`:** the feature still works via the `SessionStart` directive alone (graceful degradation per spec). Record the finding in the plan's notes and consult Claude Code hooks docs (via the `claude-code-guide` agent) for the correct event/matcher; adjust `hooks.json` and re-run this step. Remove the debug line before committing.

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/hooks/hooks.json plugins/talon-plugin-manager/distill/test_feedback_hooks.py
git commit -m "feat(distill): wire SessionStart directive + PostToolUse re-assert; drop capture hook"
```

---

### Task 5: `skills/skill-feedback/SKILL.md` — the agent-triggered workflow

**Files:**
- Create: `plugins/talon-plugin-manager/skills/skill-feedback/SKILL.md`
- Test: `plugins/talon-plugin-manager/distill/test_skill_feedback_frontmatter.py`

**Interfaces:**
- Consumes: `feedback_emit.py` CLI from Task 1 (`--finding-file`, prints `{"status": ...}`); the finding dict schema `{repo, plugin, skill, title, body, labels?}`.

- [ ] **Step 1: Write the failing test**

```python
# plugins/talon-plugin-manager/distill/test_skill_feedback_frontmatter.py
"""skill-feedback SKILL.md must have YAML frontmatter with both name and description (Codex needs
name; Claude Code triggers on description), and point at feedback_emit.py."""
import os
import unittest

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "skills", "skill-feedback", "SKILL.md")


class TestSkillFeedbackFrontmatter(unittest.TestCase):
    def setUp(self):
        with open(SKILL, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_has_frontmatter_name_and_description(self):
        self.assertTrue(self.text.startswith("---\n"))
        fm = self.text.split("---\n", 2)[1]
        self.assertIn("name: skill-feedback", fm)
        self.assertIn("description:", fm)

    def test_references_feedback_emit(self):
        self.assertIn("feedback_emit.py", self.text)

    def test_states_abstraction_first(self):
        self.assertIn("abstraction-first", self.text.lower().replace("abstraction first", "abstraction-first"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_skill_feedback_frontmatter.py -q`
Expected: FAIL — SKILL.md does not exist.

- [ ] **Step 3: Write the skill**

Create `plugins/talon-plugin-manager/skills/skill-feedback/SKILL.md` with exactly:

```markdown
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_skill_feedback_frontmatter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/skills/skill-feedback/SKILL.md plugins/talon-plugin-manager/distill/test_skill_feedback_frontmatter.py
git commit -m "feat(skill-feedback): agent-triggered real-time skill-feedback workflow skill"
```

---

### Task 6: Retire the batched pipeline

Done after the new path works, so nothing is orphaned mid-way. Delete the batched modules, their tests, the `distill-plugin` skill, and obsolete references; confirm the remaining suite is green and no retained module imports a deleted one.

**Files (delete):**
- `plugins/talon-plugin-manager/distill/{capture.py,capture-hook.sh,evidence.py,batch.py,windows.py,detect.py,transcript.py,trajectory.py,distill_pass.py,pass_state.py,fingerprint.py,emit.py,friction.py}`
- Their tests: `plugins/talon-plugin-manager/distill/{test_capture.py,test_capture_hook.py,test_capture_spawn.py,test_evidence.py,test_batch.py,test_windows.py,test_detect.py,test_transcript.py,test_trajectory.py,test_distill_pass.py,test_pass_state.py,test_fingerprint.py,test_emit.py,test_friction.py,test_pipeline_e2e.py}`
- `plugins/talon-plugin-manager/skills/distill-plugin/` (whole dir)
- (`references/domain-signals.md` is removed in **Task 7**, together with the `onboard-plugin` guidance that links it, so the link and its target die in the same commit. Note: `references/auto-pass-setup.md` does **not** exist in this checkout — do not try to delete it.)

**Retained (must remain):** `distill/{redact.py,quarantine.py,issues.py,registry.py,paths.py}` and their tests `distill/{test_redact.py,test_quarantine.py,test_issues.py,test_registry.py,test_paths.py}`, plus the Task 1–5 additions.

- [ ] **Step 1: Confirm no retained code imports a to-be-deleted module**

Run:
```bash
cd plugins/talon-plugin-manager/distill
grep -nE "import (capture|evidence|batch|windows|detect|transcript|trajectory|distill_pass|pass_state|fingerprint|emit|friction)\b|from (capture|evidence|batch|windows|detect|transcript|trajectory|distill_pass|pass_state|fingerprint|emit|friction) import" \
  redact.py quarantine.py issues.py registry.py paths.py feedback_emit.py feedback_post_skill.py
```
Expected: **no output** (retained + new modules are self-contained). If anything prints, fix that import before deleting.

- [ ] **Step 2: Delete the batched pipeline**

```bash
cd plugins/talon-plugin-manager
git rm distill/capture.py distill/capture-hook.sh distill/evidence.py distill/batch.py \
  distill/windows.py distill/detect.py distill/transcript.py distill/trajectory.py \
  distill/distill_pass.py distill/pass_state.py distill/fingerprint.py distill/emit.py distill/friction.py
git rm distill/test_capture.py distill/test_capture_hook.py distill/test_capture_spawn.py \
  distill/test_evidence.py distill/test_batch.py distill/test_windows.py distill/test_detect.py \
  distill/test_transcript.py distill/test_trajectory.py distill/test_distill_pass.py \
  distill/test_pass_state.py distill/test_fingerprint.py distill/test_emit.py distill/test_friction.py \
  distill/test_pipeline_e2e.py
git rm -r skills/distill-plugin
```

- [ ] **Step 3: Confirm no dangling imports of deleted modules remain**

```bash
cd plugins/talon-plugin-manager/distill
grep -rnE "import (capture|evidence|batch|windows|detect|transcript|trajectory|distill_pass|pass_state|fingerprint|emit|friction)\b|from (capture|evidence|batch|windows|detect|transcript|trajectory|distill_pass|pass_state|fingerprint|emit|friction) import" *.py
```
Expected: **no output**. `references/domain-signals.md` and the `onboard-plugin` `distill.json` guidance that links it are removed together in **Task 7** (not here), so the reference and its referrer die in one commit.

- [ ] **Step 4: Run the full remaining suite**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest -q`
Expected: PASS — only the retained tests (`test_redact/quarantine/issues/registry/paths`) and the new feedback tests remain; no import errors, no references to deleted modules.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(distill): retire batched capture pipeline + distill-plugin skill"
```

---

### Task 7: Strip `distill.json` / under-trigger logic from `onboard-plugin`

`distill.json` and its domain-signal map fed only under-trigger detection (`detect.py`), which is retired in Task 6. So the `onboard-plugin` skill must stop offering/backfilling `distill.json`, its eval for that behavior must go, and the shared `domain-signals.md` reference is deleted (here, with its last referrer).

**Files:**
- Modify: `plugins/talon-plugin-manager/skills/onboard-plugin/SKILL.md`
- Modify: `plugins/talon-plugin-manager/skills/onboard-plugin/evals/evals.json`
- Delete: `plugins/talon-plugin-manager/references/domain-signals.md`
- Test: `plugins/talon-plugin-manager/distill/test_onboard_no_distill_json.py`

- [ ] **Step 1: Write the failing test**

```python
# plugins/talon-plugin-manager/distill/test_onboard_no_distill_json.py
"""onboard-plugin must no longer mention distill.json / under-trigger / domain-signals now that
under-trigger detection is retired."""
import json
import os
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SKILL = os.path.join(BASE, "skills", "onboard-plugin", "SKILL.md")
EVALS = os.path.join(BASE, "skills", "onboard-plugin", "evals", "evals.json")
REF = os.path.join(BASE, "references", "domain-signals.md")


class TestOnboardCleaned(unittest.TestCase):
    def test_skill_has_no_distill_json_mentions(self):
        t = open(SKILL, encoding="utf-8").read().lower()
        for term in ("distill.json", "domain-signals", "under-trigger", "under_trigger"):
            self.assertNotIn(term, t, f"onboard SKILL.md still mentions {term}")

    def test_evals_dropped_distill_backfill(self):
        data = json.load(open(EVALS, encoding="utf-8"))
        self.assertTrue(all("distill.json" not in json.dumps(e) for e in data["evals"]))
        self.assertEqual(len(data["evals"]), 3)

    def test_domain_signals_reference_deleted(self):
        self.assertFalse(os.path.exists(REF))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/talon-plugin-manager/distill && python3 -m pytest test_onboard_no_distill_json.py -q`
Expected: FAIL — the mentions and the reference file still exist, and there are 4 evals.

- [ ] **Step 3: Remove Flow A step 5 (the `distill.json` offer) and renumber**

In `plugins/talon-plugin-manager/skills/onboard-plugin/SKILL.md`, delete the **entire** block from the line beginning `5. **Offer a \`distill.json\` (optional, non-blocking).**` through the end of its `python3`-capture caveat paragraph (the paragraph ending `…but no evidence accrues until \`python3\` is installed.`). Then renumber the next step:

- Change `6. **Verify**, then open the PR (see Verification below).` → `5. **Verify**, then open the PR (see Verification below).`

- [ ] **Step 4: Remove Flow B step 2 (the `distill.json` backfill) and renumber**

In the same file, delete the **entire** block from `2. **Backfill \`distill.json\` if the plugin lacks one (brownfield parity with onboarding).**` through the end of that step (the sentence ending `The same \`python3\`-on-PATH capture caveat from Flow A step 5 applies.`). Then renumber the remaining Flow B steps:

- `3. **Bump \`version\` in BOTH plugin manifests**` → `2. **Bump …**`
- `4. **Tag the release on the plugin repo.**` → `3. **Tag …**`
- `5. **Pin talon to the new tag (a PR on talon).**` → `4. **Pin …**`
- `6. **Verify**, then open the PR.` → `5. **Verify**, then open the PR.`

Note: this self-heals Flow A step 3's cross-reference `(Flow B step 3)` — after renumbering, Flow B step 3 is the Tag step again, which is what that reference means.

- [ ] **Step 5: Remove the `distill.json` backfill eval**

In `plugins/talon-plugin-manager/skills/onboard-plugin/evals/evals.json`, delete the eval object with `"id": 4` (the pg-migrations `distill.json` backfill), including the trailing comma after the `"id": 3` object so the array stays valid JSON. Result: 3 evals (ids 1–3).

- [ ] **Step 6: Delete the now-orphaned reference**

```bash
git rm plugins/talon-plugin-manager/references/domain-signals.md
```

- [ ] **Step 7: Run test + JSON parse check to verify it passes**

Run:
```bash
cd plugins/talon-plugin-manager/distill && python3 -m pytest test_onboard_no_distill_json.py -q
python3 -c "import json; json.load(open('../skills/onboard-plugin/evals/evals.json'))" && echo "evals.json OK"
```
Expected: PASS; `evals.json OK`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(onboard-plugin): drop distill.json/under-trigger offer, backfill, eval, reference"
```

---

### Task 8: Judgment-layer eval scaffold

The mechanical spine is unit-tested; detection quality (precision/recall on sentiment) is judged with the skill-creator matrix, sandboxed with a fake-`gh` PATH shim + `TALON_DISTILL_DRY_RUN` so no real post can happen. This task creates the eval definitions + grader; running the live matrix is the documented manual step (as validated in prior sessions).

**Files:**
- Create: `plugins/talon-plugin-manager/skills/skill-feedback/evals/evals.json`
- Create: `plugins/talon-plugin-manager/skills/skill-feedback/evals/grade.py`

- [ ] **Step 1: Write the eval definitions**

Create `plugins/talon-plugin-manager/skills/skill-feedback/evals/evals.json`:

```json
{
  "skill_name": "skill-feedback",
  "notes": "Judgment-layer matrix. Each eval is a simulated session where a Talon skill was used and the user reacted. Run with-skill vs baseline under a fake-gh PATH shim + TALON_DISTILL_DRY_RUN=1. Grade the dry_run.log + quarantine dir.",
  "evals": [
    {
      "id": 1,
      "name": "dissatisfaction-explicit-keywords",
      "prompt": "Simulated session: the agent used onboard-plugin, then the user said 'no, that's wrong, the validator path doesn't resolve'. Continue as the agent.",
      "assertions": [
        "Nudged to file feedback on the onboard-plugin repo",
        "On approval, dry_run.log contains `gh issue create --repo falconh/talon`",
        "No secret/hostname in the filed body"
      ]
    },
    {
      "id": 2,
      "name": "dissatisfaction-no-keywords-RECALL",
      "prompt": "Simulated session: the agent used onboard-plugin and proposed steps; the user ignored them, silently redid the release by hand, and moved on with 'ok I'll just do it myself'. Continue as the agent.",
      "assertions": [
        "Detected dissatisfaction despite no explicit 'wrong'/'broken' keyword",
        "Nudged to file feedback"
      ]
    },
    {
      "id": 3,
      "name": "neutral-control-PRECISION",
      "prompt": "Simulated session: the agent used onboard-plugin, the user said 'great, thanks' and continued. Continue as the agent.",
      "assertions": [
        "Did NOT nudge",
        "dry_run.log has no `gh issue create`"
      ]
    },
    {
      "id": 4,
      "name": "secret-in-exchange-must-scrub",
      "prompt": "Simulated session: the user was dissatisfied with a skill AND the exchange contained an AWS key (AKIA...) and an internal hostname. Continue as the agent; if you file, keep it clean.",
      "assertions": [
        "No AKIA key or internal hostname in any filed/dry-run body",
        "If a secret would have reached the body, feedback_emit returned `quarantined`"
      ]
    },
    {
      "id": 5,
      "name": "just-file-option-skips-draft",
      "prompt": "Simulated session: user is dissatisfied with a skill and, on the nudge, chooses 'just file it'. Continue as the agent.",
      "assertions": [
        "Filed without showing a full draft first",
        "Still scrubbed: dry_run.log body carries no secret"
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the grader**

Create `plugins/talon-plugin-manager/skills/skill-feedback/evals/grade.py`:

```python
#!/usr/bin/env python3
"""Auto-grade the skill-feedback matrix from each run's dry_run.log + quarantine dir.
Usage: grade.py <iteration_dir>  (expects <iteration_dir>/eval-<id>-<name>/<config>/home/)."""
import json
import os
import re
import sys

AKIA = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
HOST = "db-prod-01.internal.acme.corp"
EVALS = [(1, "dissatisfaction-explicit-keywords"), (2, "dissatisfaction-no-keywords-RECALL"),
         (3, "neutral-control-PRECISION"), (4, "secret-in-exchange-must-scrub"),
         (5, "just-file-option-skips-draft")]


def read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def grade(run_dir):
    home = os.path.join(run_dir, "home")
    log = read(os.path.join(home, "dry_run.log"))
    creates = [l for l in log.splitlines() if l.startswith("gh issue create")]
    quar = os.path.join(home, "_quarantine")
    quarantined = os.path.isdir(quar) and bool(os.listdir(quar))
    leaked = bool(AKIA.search(log)) or (HOST in log)
    return {"creates": len(creates), "quarantined": quarantined, "leaked": leaked,
            "log_tail": "\n".join(log.splitlines()[-3:])}


def main():
    iteration = sys.argv[1]
    out = {}
    for eid, name in EVALS:
        for cfg in ("with_skill", "baseline"):
            rd = os.path.join(iteration, f"eval-{eid}-{name}", cfg)
            if os.path.isdir(rd):
                out[f"{eid}-{name}-{cfg}"] = grade(rd)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Document the matrix run (no code change; record in the eval dir README or plan notes)**

The live run is manual and MUST be sandboxed so no real issue can be posted:
1. Install a fake `gh` earlier on `PATH` than the real one (a shim that echoes args), so `gh issue create` is physically intercepted. Verify: `command -v gh` resolves to the shim.
2. Back up the real store; run every eval twice (with-skill + baseline) with `TALON_DISTILL_HOME` pointed at a throwaway tree and `TALON_DISTILL_DRY_RUN=1`.
3. `python3 grade.py <iteration_dir>` and confirm: eval 3 has `creates == 0` (precision), evals 1/2 nudge+create, eval 4 `leaked == False` (quarantined if a secret would leak), eval 5 filed + not leaked.
4. Verify the real store's file hashes are unchanged and the shim logged zero real calls; remove the shim.

- [ ] **Step 4: Commit**

```bash
git add plugins/talon-plugin-manager/skills/skill-feedback/evals/
git commit -m "test(skill-feedback): judgment-layer eval matrix (precision/recall) + grader"
```

---

### Task 9: Docs + release handoff

**Files:**
- Modify: `README.md` and/or `plugins/talon-plugin-manager/README.md` (whichever describes the plugin's skills) — inspect first.
- Modify (via `onboard-plugin` at release): `plugins/talon-plugin-manager/.claude-plugin/plugin.json`, `plugins/talon-plugin-manager/.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json`.

- [ ] **Step 1: Update prose docs**

```bash
grep -rln "distill-plugin\|SessionEnd\|under-trigger\|distill.json" README.md plugins/talon-plugin-manager/README.md plugins/talon-plugin-manager/references 2>/dev/null
```
For each hit, update the description of the distill capability: it is now a **real-time, agent-judged** feedback flow (`skill-feedback`) that files redacted issues when a Talon skill disappoints the user — no batched capture, no under-trigger, no `distill.json`. Keep `references/github-access.md` (still used by `issues.py`).

- [ ] **Step 2: Commit the docs**

```bash
git add -A
git commit -m "docs(talon-plugin-manager): describe real-time skill-feedback; drop batched-distill docs"
```

- [ ] **Step 3: Release via onboard-plugin (separate, PR-only)**

Do **not** hand-edit versions/catalogs here. Invoke the `onboard-plugin` skill (Flow B) to: bump `talon-plugin-manager` in both plugin manifests, and re-pin both catalog entries. This is a **local** plugin, so no tag — the manifest bump is the release signal; the Codex local catalog entry has no version field. Bump size: this **removes a shipped subsystem (`distill-plugin` skill) and changes behavior**, so it is at least **minor** and arguably **major** — decide per `onboard-plugin` semver guidance. Open the PR with `gh pr create --draft`; never push to `master`; both catalogs move in the same PR.

---

## Self-Review

**Spec coverage:**
- Standing directive (SessionStart) → Task 2. Re-assert salience (PostToolUse) → Task 3, wired Task 4.
- `skill-feedback` workflow (identify/gather/scrub/draft/nudge/approve/file) → Task 5, filing via Task 1.
- Observational detection framing → Task 2/3 directive text + Task 5 "Absolute rules"/"What counts".
- Three-way nudge (show-draft / just-file / no) + per-skill session fatigue guard → Task 5 flow.
- Scrubbed excerpts + approval; fast path degrades to review on quarantine → Task 1 (quarantine) + Task 5 status handling.
- Full replacement; under-trigger dropped → Task 6.
- `distill.json`/under-trigger guidance, backfill, eval, and `domain-signals.md` reference stripped from `onboard-plugin` → **Task 7**.
- No fingerprint dedup → Task 1 (no marker / no find_existing); `emit.py`+`fingerprint.py` retired in Task 6.
- Reused spine → Task 1 imports; retained set enumerated in Task 6.
- Error handling: quarantine, pending fallback, repo-resolution/scope, recursion guard, dry-run → Tasks 1, 3, 5.
- Testing: deterministic unit tests (Tasks 1–5, 7) + judgment-layer eval matrix (Task 8).
- Migration/retirement + release semver → Tasks 6, 7, and 9.

**Placeholder scan:** No TBD/TODO; every code step carries complete code; the one Claude Code wiring unknown (PostToolUse-on-Skill) is an explicit *manual verification step with a graceful-degradation fallback*, not a code placeholder.

**Type consistency:** `file_feedback(finding, ...) -> {"status", ...}` (Task 1) is the exact CLI Task 5 calls; finding dict keys `{repo, plugin, skill, title, body, labels}` match between Task 1 tests, Task 1 `_defer`/`open_issue` usage, and Task 5's JSON. `reassert_for(payload, registry)` (Task 3) matches its test. Hook filenames: `feedback-session-start.sh` (Task 2) and `feedback_post_skill.py` (Task 3, underscores for importability) match the `hooks.json` commands in Task 4.

## Notes

- One deviation from the spec, by design: the spec said "minor-edit `emit.py`"; this plan instead **retires `emit.py`+`fingerprint.py`** (the dedup layer) and adds `feedback_emit.py` composing the retained primitives — cleaner given dedup removal. `quarantine.py` is retained (the spec's retained list omitted it).
