# Talon Plugin Distillation — Capture (Phase A) + Packaging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `talon-onboarding` plugin to `talon-plugin-manager` and add a `SessionEnd` hook that, on every Claude Code session, deterministically captures evidence about Talon-plugin usage, friction, and under-trigger to a rolling per-plugin store on disk.

**Architecture:** A pure-stdlib Python package (`distill/`) bundled in the renamed plugin holds the capture engine — a registry loader, a transcript parser, usage/domain detection, a friction pre-scan, an evidence-store writer, and a batch-threshold checker. A plugin-level `SessionEnd` hook invokes a thin CLI (`distill/capture.py`) that wires these together and appends one evidence record per used/under-triggered Talon plugin. No LLM runs in this phase. The downstream distill pass (Phase B) that turns evidence into GitHub issues is a separate plan.

**Tech Stack:** Python 3.13 standard library only (`json`, `re`, `pathlib`, `dataclasses`, `argparse`, `unittest`). No third-party dependencies. Claude Code plugin hooks (`hooks/hooks.json`, `SessionEnd`). Tests are `unittest.TestCase`, run with `python3 -m unittest discover`.

## Global Constraints

- **Python 3.13+, standard library only.** No pip dependencies. (Uses `pathlib.PurePath.full_match`, added in 3.13, for `**` globs.)
- **Plugin scope is `@talon` only.** The Talon registry = plugin names whose key in `~/.claude/plugins/installed_plugins.json` ends in `@talon`.
- **Dual-catalog sync.** Every plugin appears in BOTH `.claude-plugin/marketplace.json` (Claude) and `.agents/plugins/marketplace.json` (Codex) with the same source kind; local plugins carry BOTH `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` at matching versions. The validator `validate_talon.py` enforces this.
- **Stable skill names.** The skill `onboard-plugin` keeps its name (renaming a skill breaks installs). Only the *plugin* is renamed; this is a **major** version bump (`1.1.0` → `2.0.0`).
- **PR-only releases.** This plan produces the renamed, validated state in the worktree. Tagging/pinning/PR is done afterward by the maintainer via the `onboard-plugin` flow — not automated here.
- **Evidence store path:** `~/.claude/talon-distill/evidence/<plugin>.jsonl` (append-only JSONL, one record per line).
- **No network, no LLM, no secrets read in Phase A.** Capture is deterministic local file I/O only.

---

## File Structure

After this plan, the renamed plugin looks like:

```
plugins/talon-plugin-manager/
  .claude-plugin/plugin.json        # renamed, v2.0.0, + "hooks" ref
  .codex-plugin/plugin.json         # renamed, v2.0.0
  hooks/hooks.json                  # NEW — SessionEnd → distill/capture.py
  distill/                          # NEW — capture engine (stdlib only)
    registry.py                     # load @talon registry from installed_plugins.json
    transcript.py                   # parse session JSONL → tool calls + user texts
    detect.py                       # usage (Skill calls) + domain (distill.json) detection
    friction.py                     # deterministic friction pre-scan → hints
    evidence.py                     # evidence record + append writer
    batch.py                        # unprocessed-count threshold checker
    capture.py                      # CLI: stdin hook payload → evidence records
    test_registry.py  test_transcript.py  test_detect.py
    test_friction.py  test_evidence.py    test_batch.py  test_capture.py
    fixtures/
      installed_plugins.json
      transcript_usage.jsonl
      transcript_under_trigger.jsonl
      distill.json
  skills/onboard-plugin/            # moved unchanged from talon-onboarding
    ...
```

Catalogs/manifests/README/reference-doc updated to the new name (Task 1).

---

## Task 1: Rename plugin `talon-onboarding` → `talon-plugin-manager`

**Files:**
- Move: `plugins/talon-onboarding/` → `plugins/talon-plugin-manager/` (via `git mv`)
- Modify: `plugins/talon-plugin-manager/.claude-plugin/plugin.json`
- Modify: `plugins/talon-plugin-manager/.codex-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json:30-37` (the `talon-onboarding` entry)
- Modify: `.agents/plugins/marketplace.json:32-41` (the `talon-onboarding` entry)
- Modify: `plugins/talon-plugin-manager/skills/onboard-plugin/references/release-and-pr-workflow.md:51`
- Modify: `README.md:15,22,25`
- Validate: `plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the plugin directory `plugins/talon-plugin-manager/` and a passing `validate_talon.py`, which every later task builds inside.

- [ ] **Step 1: Move the plugin directory**

```bash
git mv plugins/talon-onboarding plugins/talon-plugin-manager
```

- [ ] **Step 2: Update the Claude manifest**

Edit `plugins/talon-plugin-manager/.claude-plugin/plugin.json` — set `name`, `version`, `description`, add `distillation` to keywords, and add a `hooks` reference (used in Task 8):

```json
{
  "name": "talon-plugin-manager",
  "description": "Maintainer plugin for the Talon marketplace: onboard and release plugins with dual Claude Code + Codex support (naming, semver bump + tag, PR-only), and distill real session usage of Talon plugins into improvement findings.",
  "version": "2.0.0",
  "author": { "name": "falconh" },
  "homepage": "https://github.com/falconh/talon",
  "repository": "https://github.com/falconh/talon",
  "license": "MIT",
  "keywords": ["talon", "marketplace", "plugin", "onboarding", "distillation", "claude-code", "codex", "release", "semver"],
  "skills": "./skills",
  "hooks": "./hooks/hooks.json"
}
```

- [ ] **Step 3: Update the Codex manifest**

Edit `plugins/talon-plugin-manager/.codex-plugin/plugin.json` — set `name`, `version`, `description`, keywords, and `interface.displayName` (Codex ignores `hooks`, so do not add it here):

```json
{
  "name": "talon-plugin-manager",
  "version": "2.0.0",
  "description": "Maintainer plugin for the Talon marketplace: onboard and release plugins with dual Claude Code + Codex support (naming, semver bump + tag, PR-only), and distill real session usage of Talon plugins into improvement findings.",
  "author": { "name": "falconh" },
  "license": "MIT",
  "keywords": ["talon", "marketplace", "plugin", "onboarding", "distillation", "claude-code", "codex", "release", "semver"],
  "skills": "./skills/",
  "interface": {
    "displayName": "Talon Plugin Manager",
    "shortDescription": "Onboard, release, and distill plugins on the Talon marketplace.",
    "category": "Development"
  }
}
```

- [ ] **Step 4: Update both catalogs**

In `.claude-plugin/marketplace.json`, change the `talon-onboarding` entry to:

```json
    {
      "name": "talon-plugin-manager",
      "source": "./plugins/talon-plugin-manager",
      "description": "Maintainer plugin: onboard, release, and distill plugins on the Talon marketplace (dual Claude Code + Codex, naming, semver bump + tag, PR-only).",
      "version": "2.0.0",
      "author": { "name": "falconh" }
    }
```

In `.agents/plugins/marketplace.json`, change the `talon-onboarding` entry to:

```json
    {
      "name": "talon-plugin-manager",
      "source": { "source": "local", "path": "./plugins/talon-plugin-manager" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Development"
    }
```

- [ ] **Step 5: Update doc references**

In `plugins/talon-plugin-manager/skills/onboard-plugin/references/release-and-pr-workflow.md:51` and `README.md` lines 15, 22, 25, replace every `talon-onboarding` path/name with `talon-plugin-manager`. Verify none remain:

```bash
grep -rn "talon-onboarding" . | grep -vE '/\.git/|docs/superpowers/'
```
Expected: no output.

- [ ] **Step 6: Validate the renamed marketplace**

Run: `python3 plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py --root .`
Expected: exits `0`, prints no `ERROR:` lines (warnings allowed).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename talon-onboarding plugin to talon-plugin-manager (major)"
```

---

## Task 2: Registry loader (`distill/registry.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/registry.py`
- Create: `plugins/talon-plugin-manager/distill/fixtures/installed_plugins.json`
- Test: `plugins/talon-plugin-manager/distill/test_registry.py`

**Interfaces:**
- Consumes: `~/.claude/plugins/installed_plugins.json` shape `{"version":2,"plugins":{"<name>@<marketplace>":[{"installPath":...,"version":...}]}}`.
- Produces: `load_talon_registry(path: str) -> dict[str, str]` returning `{plugin_name: install_path}` for every key ending in `@talon` (latest entry's `installPath`). Later tasks call `set(registry)` for names and use `installPath` to locate a plugin's `distill.json`.

- [ ] **Step 1: Write the fixture**

Create `plugins/talon-plugin-manager/distill/fixtures/installed_plugins.json`:

```json
{
  "version": 2,
  "plugins": {
    "superpowers@claude-plugins-official": [{ "installPath": "/x/superpowers/6.0.2", "version": "6.0.2" }],
    "talon-plugin-manager@talon": [{ "installPath": "/x/talon/talon-plugin-manager", "version": "2.0.0" }],
    "terraform-module-steering@talon": [{ "installPath": "/x/tms/1.1.0", "version": "1.1.0" }]
  }
}
```

- [ ] **Step 2: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_registry.py`:

```python
import os
import unittest
from registry import load_talon_registry

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "installed_plugins.json")


class TestRegistry(unittest.TestCase):
    def test_only_talon_plugins(self):
        reg = load_talon_registry(FIX)
        self.assertEqual(set(reg), {"talon-plugin-manager", "terraform-module-steering"})

    def test_maps_name_to_install_path(self):
        reg = load_talon_registry(FIX)
        self.assertEqual(reg["terraform-module-steering"], "/x/tms/1.1.0")

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_talon_registry("/no/such/file.json"), {})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'registry'`.

- [ ] **Step 4: Write the implementation**

Create `plugins/talon-plugin-manager/distill/registry.py`:

```python
"""Load the set of installed Talon-marketplace plugins from installed_plugins.json."""
from __future__ import annotations
import json


def load_talon_registry(path: str) -> dict[str, str]:
    """Return {plugin_name: install_path} for every plugin installed from the
    'talon' marketplace (key '<name>@talon' in installed_plugins.json)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for key, installs in (data.get("plugins") or {}).items():
        name, _, marketplace = key.rpartition("@")
        if marketplace != "talon" or not name:
            continue
        install_path = ""
        if isinstance(installs, list) and installs:
            install_path = installs[-1].get("installPath", "")
        out[name] = install_path
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_registry.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/distill/registry.py plugins/talon-plugin-manager/distill/test_registry.py plugins/talon-plugin-manager/distill/fixtures/installed_plugins.json
git commit -m "feat(distill): load @talon registry from installed_plugins.json"
```

---

## Task 3: Transcript parser (`distill/transcript.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/transcript.py`
- Create: `plugins/talon-plugin-manager/distill/fixtures/transcript_usage.jsonl`
- Test: `plugins/talon-plugin-manager/distill/test_transcript.py`

**Interfaces:**
- Consumes: a session transcript JSONL. Each line is an object; `obj["message"]["content"]` may be a list of blocks. `tool_use` blocks have `{"type":"tool_use","id","name","input"}`; `tool_result` blocks have `{"type":"tool_result","tool_use_id","content","is_error"?}`; human turns are user-role messages whose content is a string or contains `{"type":"text","text":...}` blocks.
- Produces:
  - `@dataclass ToolCall(id: str, name: str, input: dict, is_error: bool, result_text: str)`
  - `@dataclass ParsedTranscript(tool_calls: list[ToolCall], user_texts: list[str])`
  - `parse_transcript(path: str) -> ParsedTranscript`

  Consumed by Task 4 (`detect`) and Task 5 (`friction`).

- [ ] **Step 1: Write the fixture**

Create `plugins/talon-plugin-manager/distill/fixtures/transcript_usage.jsonl` (a Skill call to a Talon plugin, a successful Bash call, and a failed Bash call):

```jsonl
{"type":"user","message":{"role":"user","content":"help me onboard a plugin"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"t1","name":"Skill","input":{"skill":"talon-plugin-manager:onboard-plugin"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"Launching skill"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"t2","name":"Bash","input":{"command":"python3 validate_talon.py"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t2","content":"OK"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"t3","name":"Bash","input":{"command":"terraform plan"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t3","content":"Error: boom","is_error":true}]}}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"that's wrong, try again"}]}}
```

- [ ] **Step 2: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_transcript.py`:

```python
import os
import unittest
from transcript import parse_transcript

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "transcript_usage.jsonl")


class TestTranscript(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_transcript(FIX)

    def test_collects_tool_calls(self):
        names = [c.name for c in self.parsed.tool_calls]
        self.assertEqual(names, ["Skill", "Bash", "Bash"])

    def test_joins_result_and_error_by_id(self):
        by_id = {c.id: c for c in self.parsed.tool_calls}
        self.assertFalse(by_id["t2"].is_error)
        self.assertTrue(by_id["t3"].is_error)
        self.assertIn("boom", by_id["t3"].result_text)

    def test_extracts_human_texts_not_tool_results(self):
        self.assertEqual(self.parsed.user_texts, ["help me onboard a plugin", "that's wrong, try again"])

    def test_missing_file_is_empty(self):
        p = parse_transcript("/no/file.jsonl")
        self.assertEqual(p.tool_calls, [])
        self.assertEqual(p.user_texts, [])
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_transcript.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'transcript'`.

- [ ] **Step 4: Write the implementation**

Create `plugins/talon-plugin-manager/distill/transcript.py`:

```python
"""Parse a Claude Code session transcript (JSONL) into tool calls + human texts."""
from __future__ import annotations
import json
from dataclasses import dataclass, field

_CLIP = 400


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    is_error: bool = False
    result_text: str = ""


@dataclass
class ParsedTranscript:
    tool_calls: list[ToolCall] = field(default_factory=list)
    user_texts: list[str] = field(default_factory=list)


def _blocks(obj: dict) -> list:
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def parse_transcript(path: str) -> ParsedTranscript:
    out = ParsedTranscript()
    by_id: dict[str, ToolCall] = {}
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = (obj.get("message") or {}).get("role")
            had_tool_result = False
            for b in _blocks(obj):
                if not isinstance(b, dict):
                    continue
                btype = b.get("type")
                if btype == "tool_use":
                    call = ToolCall(id=b.get("id", ""), name=b.get("name", ""), input=b.get("input") or {})
                    out.tool_calls.append(call)
                    if call.id:
                        by_id[call.id] = call
                elif btype == "tool_result":
                    had_tool_result = True
                    call = by_id.get(b.get("tool_use_id", ""))
                    if call is not None:
                        call.is_error = bool(b.get("is_error", False))
                        call.result_text = str(b.get("content", ""))[:_CLIP]
                elif btype == "text" and role == "user":
                    text = (b.get("text") or "").strip()
                    if text:
                        out.user_texts.append(text)
            # ignore: a user message that only carried tool_results is not a human turn
            _ = had_tool_result
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_transcript.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/distill/transcript.py plugins/talon-plugin-manager/distill/test_transcript.py plugins/talon-plugin-manager/distill/fixtures/transcript_usage.jsonl
git commit -m "feat(distill): parse session transcript into tool calls and human texts"
```

---

## Task 4: Usage + domain detection (`distill/detect.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/detect.py`
- Create: `plugins/talon-plugin-manager/distill/fixtures/distill.json`
- Create: `plugins/talon-plugin-manager/distill/fixtures/transcript_under_trigger.jsonl`
- Test: `plugins/talon-plugin-manager/distill/test_detect.py`

**Interfaces:**
- Consumes: `list[ToolCall]` from Task 3; the registry dict from Task 2; per-plugin `distill.json` of shape `{"domain_globs":[...], "domain_cmds":[...]}`.
- Produces:
  - `detect_usage(calls: list[ToolCall], registry_names: set[str]) -> set[str]` — Talon plugins invoked via a `Skill` call (prefix before `:` in `input["skill"]`).
  - `load_domain_map(registry: dict[str, str]) -> dict[str, dict]` — reads `<install_path>/distill.json` per plugin; missing file ⇒ omitted.
  - `detect_domain(calls: list[ToolCall], domain_map: dict[str, dict]) -> set[str]` — plugins whose `domain_cmds` match a Bash command or whose `domain_globs` match an edited/written/read file path.
  - `under_triggered(calls, registry_names, domain_map) -> set[str]` = `detect_domain(...) - detect_usage(...)`.

- [ ] **Step 1: Write the fixtures**

Create `plugins/talon-plugin-manager/distill/fixtures/distill.json`:

```json
{ "domain_globs": ["**/*.tf"], "domain_cmds": ["terraform", "tofu"] }
```

Create `plugins/talon-plugin-manager/distill/fixtures/transcript_under_trigger.jsonl` (terraform domain activity, but NO Talon skill fired):

```jsonl
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"u1","name":"Write","input":{"file_path":"infra/main.tf"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"u1","content":"written"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"u2","name":"Bash","input":{"command":"terraform init"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"u2","content":"ok"}]}}
```

- [ ] **Step 2: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_detect.py`:

```python
import os
import unittest
from transcript import parse_transcript, ToolCall
from detect import detect_usage, detect_domain, under_triggered, load_domain_map

HERE = os.path.dirname(__file__)
USAGE = os.path.join(HERE, "fixtures", "transcript_usage.jsonl")
UNDER = os.path.join(HERE, "fixtures", "transcript_under_trigger.jsonl")
FIXDIR = os.path.join(HERE, "fixtures")

DMAP = {"terraform-module-steering": {"globs": ["**/*.tf"], "cmds": ["terraform", "tofu"]}}


class TestDetect(unittest.TestCase):
    def test_detect_usage_from_skill_call(self):
        calls = parse_transcript(USAGE).tool_calls
        self.assertEqual(detect_usage(calls, {"talon-plugin-manager", "x"}), {"talon-plugin-manager"})

    def test_detect_domain_by_cmd_and_glob(self):
        calls = parse_transcript(UNDER).tool_calls
        self.assertEqual(detect_domain(calls, DMAP), {"terraform-module-steering"})

    def test_under_triggered_when_domain_but_no_skill(self):
        calls = parse_transcript(UNDER).tool_calls
        self.assertEqual(under_triggered(calls, set(), DMAP), {"terraform-module-steering"})

    def test_not_under_triggered_when_skill_used(self):
        calls = parse_transcript(UNDER).tool_calls
        self.assertEqual(under_triggered(calls, {"terraform-module-steering"}, DMAP), set())

    def test_load_domain_map_reads_distill_json(self):
        reg = {"terraform-module-steering": FIXDIR}  # distill.json lives in fixtures/
        dmap = load_domain_map(reg)
        self.assertEqual(dmap["terraform-module-steering"]["cmds"], ["terraform", "tofu"])
        self.assertEqual(dmap["terraform-module-steering"]["globs"], ["**/*.tf"])

    def test_load_domain_map_skips_missing(self):
        self.assertEqual(load_domain_map({"x": "/no/such/dir"}), {})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'detect'`.

- [ ] **Step 4: Write the implementation**

Create `plugins/talon-plugin-manager/distill/detect.py`:

```python
"""Detect which Talon plugins were used (Skill calls) or under-triggered (domain
activity with no skill fired) in a parsed session."""
from __future__ import annotations
import json
import os
import re
from pathlib import PurePath

from transcript import ToolCall

_PATH_TOOLS = {"Edit", "Write", "Read", "NotebookEdit"}


def detect_usage(calls: list[ToolCall], registry_names: set[str]) -> set[str]:
    used: set[str] = set()
    for c in calls:
        if c.name != "Skill":
            continue
        skill = str(c.input.get("skill", ""))
        plugin = skill.split(":", 1)[0]
        if plugin in registry_names:
            used.add(plugin)
    return used


def load_domain_map(registry: dict[str, str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for plugin, install_path in registry.items():
        if not install_path:
            continue
        cfg_path = os.path.join(install_path, "distill.json")
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        out[plugin] = {
            "globs": list(cfg.get("domain_globs") or []),
            "cmds": list(cfg.get("domain_cmds") or []),
        }
    return out


def _file_paths(calls: list[ToolCall]) -> list[str]:
    paths = []
    for c in calls:
        if c.name in _PATH_TOOLS:
            p = c.input.get("file_path") or c.input.get("notebook_path")
            if p:
                paths.append(str(p))
    return paths


def _commands(calls: list[ToolCall]) -> list[str]:
    return [str(c.input.get("command", "")) for c in calls if c.name == "Bash"]


def detect_domain(calls: list[ToolCall], domain_map: dict[str, dict]) -> set[str]:
    paths = _file_paths(calls)
    commands = _commands(calls)
    active: set[str] = set()
    for plugin, sig in domain_map.items():
        cmd_hit = any(
            re.search(rf"\b{re.escape(cmd)}\b", command)
            for cmd in sig.get("cmds", [])
            for command in commands
        )
        glob_hit = any(
            PurePath(path).full_match(glob)
            for glob in sig.get("globs", [])
            for path in paths
        )
        if cmd_hit or glob_hit:
            active.add(plugin)
    return active


def under_triggered(calls: list[ToolCall], registry_names: set[str], domain_map: dict[str, dict]) -> set[str]:
    return detect_domain(calls, domain_map) - detect_usage(calls, registry_names)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_detect.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add plugins/talon-plugin-manager/distill/detect.py plugins/talon-plugin-manager/distill/test_detect.py plugins/talon-plugin-manager/distill/fixtures/distill.json plugins/talon-plugin-manager/distill/fixtures/transcript_under_trigger.jsonl
git commit -m "feat(distill): detect Talon plugin usage and under-trigger"
```

---

## Task 5: Friction pre-scan (`distill/friction.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/friction.py`
- Test: `plugins/talon-plugin-manager/distill/test_friction.py`

**Interfaces:**
- Consumes: `list[ToolCall]` and `list[str]` (user texts) from Task 3.
- Produces:
  - `@dataclass FrictionHints(has_tool_errors: bool, error_count: int, repeated_error_count: int, retry: bool, correction: bool, abandonment: bool)`
  - `scan_friction(calls: list[ToolCall], user_texts: list[str]) -> FrictionHints`
  - `FrictionHints.as_dict() -> dict` (for the evidence record in Task 6).

  Friction policy: a *hard* signal exists when `has_tool_errors` or `repeated_error_count >= 2`; *soft* signals are `retry`, `correction`, `abandonment`. The fire decision itself is Phase B; Phase A only records these hints.

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_friction.py`:

```python
import unittest
from transcript import ToolCall
from friction import scan_friction


def err(name, sig):
    return ToolCall(id="x", name=name, input={"command": name}, is_error=True, result_text=sig)


class TestFriction(unittest.TestCase):
    def test_no_friction_clean_session(self):
        h = scan_friction([ToolCall("a", "Bash", {"command": "ls"}, False, "ok")], ["thanks"])
        self.assertFalse(h.has_tool_errors)
        self.assertEqual(h.repeated_error_count, 0)
        self.assertFalse(h.correction)

    def test_detects_errors_and_repeats(self):
        calls = [err("Bash", "Error: boom"), err("Bash", "Error: boom")]
        h = scan_friction(calls, [])
        self.assertTrue(h.has_tool_errors)
        self.assertEqual(h.error_count, 2)
        self.assertEqual(h.repeated_error_count, 2)

    def test_detects_correction_language(self):
        h = scan_friction([], ["No, that's wrong"])
        self.assertTrue(h.correction)

    def test_detects_retry_repeated_command(self):
        c = [ToolCall("1", "Bash", {"command": "terraform apply"}, False, "x"),
             ToolCall("2", "Bash", {"command": "terraform apply"}, False, "x")]
        self.assertTrue(scan_friction(c, []).retry)

    def test_detects_abandonment(self):
        self.assertTrue(scan_friction([], ["ok never mind, forget it"]).abandonment)

    def test_as_dict_roundtrips_keys(self):
        d = scan_friction([], []).as_dict()
        self.assertEqual(set(d), {"has_tool_errors", "error_count", "repeated_error_count", "retry", "correction", "abandonment"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_friction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/friction.py`:

```python
"""Deterministic friction pre-scan over a parsed session."""
from __future__ import annotations
import re
from collections import Counter
from dataclasses import asdict, dataclass

from transcript import ToolCall

_CORRECTION = re.compile(
    r"\b(no,|not quite|that'?s wrong|that is wrong|actually|undo|revert|"
    r"that didn'?t work|still (failing|broken|wrong))\b",
    re.IGNORECASE,
)
_ABANDON = re.compile(
    r"\b(never ?mind|forget it|give up|stop,?|let'?s move on|drop it)\b",
    re.IGNORECASE,
)


@dataclass
class FrictionHints:
    has_tool_errors: bool = False
    error_count: int = 0
    repeated_error_count: int = 0
    retry: bool = False
    correction: bool = False
    abandonment: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _error_signature(c: ToolCall) -> str:
    return f"{c.name}:{c.result_text[:60]}"


def scan_friction(calls: list[ToolCall], user_texts: list[str]) -> FrictionHints:
    errors = [c for c in calls if c.is_error]
    sig_counts = Counter(_error_signature(c) for c in errors)
    cmd_counts = Counter(
        str(c.input.get("command", "")) for c in calls if c.name == "Bash" and c.input.get("command")
    )
    joined = "\n".join(user_texts)
    return FrictionHints(
        has_tool_errors=bool(errors),
        error_count=len(errors),
        repeated_error_count=max(sig_counts.values(), default=0),
        retry=any(n >= 2 for n in cmd_counts.values()),
        correction=bool(_CORRECTION.search(joined)),
        abandonment=bool(_ABANDON.search(joined)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_friction.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/friction.py plugins/talon-plugin-manager/distill/test_friction.py
git commit -m "feat(distill): deterministic friction pre-scan"
```

---

## Task 6: Evidence store (`distill/evidence.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/evidence.py`
- Test: `plugins/talon-plugin-manager/distill/test_evidence.py`

**Interfaces:**
- Consumes: friction dict from Task 5; plugin name, session id, kind.
- Produces:
  - `@dataclass EvidenceRecord(session_id, plugin, kind, skills_used, friction, captured_at, transcript_path, processed=False)` where `kind` is `"usage"` or `"under_trigger"`.
  - `append_evidence(store_dir: str, rec: EvidenceRecord) -> str` — appends one JSON line to `<store_dir>/<plugin>.jsonl`, creating dirs; returns the file path.
  - `read_evidence(store_dir: str, plugin: str) -> list[dict]` — reads all records (used by Task 7).
  - `EVIDENCE_DIR` default `~/.claude/talon-distill/evidence`.

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_evidence.py`:

```python
import json
import os
import tempfile
import unittest
from evidence import EvidenceRecord, append_evidence, read_evidence


class TestEvidence(unittest.TestCase):
    def test_append_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            rec = EvidenceRecord(
                session_id="s1", plugin="terraform-module-steering", kind="under_trigger",
                skills_used=[], friction={"has_tool_errors": True}, captured_at="2026-06-17T00:00:00Z",
                transcript_path="/t.jsonl",
            )
            path = append_evidence(d, rec)
            self.assertTrue(path.endswith("terraform-module-steering.jsonl"))
            rows = read_evidence(d, "terraform-module-steering")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], "under_trigger")
            self.assertFalse(rows[0]["processed"])

    def test_append_is_additive(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(3):
                append_evidence(d, EvidenceRecord("s%d" % i, "p", "usage", [], {}, "t", "/t"))
            self.assertEqual(len(read_evidence(d, "p")), 3)

    def test_read_missing_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(read_evidence(d, "nope"), [])

    def test_lines_are_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            append_evidence(d, EvidenceRecord("s", "p", "usage", ["x"], {}, "t", "/t"))
            with open(os.path.join(d, "p.jsonl")) as fh:
                json.loads(fh.readline())  # raises if invalid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_evidence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evidence'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/evidence.py`:

```python
"""Append-only per-plugin evidence store at ~/.claude/talon-distill/evidence/<plugin>.jsonl."""
from __future__ import annotations
import json
import os
from dataclasses import asdict, dataclass, field

EVIDENCE_DIR = os.path.expanduser("~/.claude/talon-distill/evidence")


@dataclass
class EvidenceRecord:
    session_id: str
    plugin: str
    kind: str  # "usage" | "under_trigger"
    skills_used: list
    friction: dict
    captured_at: str
    transcript_path: str
    processed: bool = False


def _store_path(store_dir: str, plugin: str) -> str:
    return os.path.join(store_dir, f"{plugin}.jsonl")


def append_evidence(store_dir: str, rec: EvidenceRecord) -> str:
    os.makedirs(store_dir, exist_ok=True)
    path = _store_path(store_dir, rec.plugin)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
    return path


def read_evidence(store_dir: str, plugin: str) -> list[dict]:
    path = _store_path(store_dir, plugin)
    rows: list[dict] = []
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return rows
    with fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_evidence.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/evidence.py plugins/talon-plugin-manager/distill/test_evidence.py
git commit -m "feat(distill): append-only per-plugin evidence store"
```

---

## Task 7: Batch-threshold checker (`distill/batch.py`)

**Files:**
- Create: `plugins/talon-plugin-manager/distill/batch.py`
- Test: `plugins/talon-plugin-manager/distill/test_batch.py`

**Interfaces:**
- Consumes: `read_evidence` from Task 6.
- Produces:
  - `unprocessed_count(store_dir: str, plugin: str) -> int` — number of records with `processed == False`.
  - `should_run_batch(store_dir: str, plugin: str, n_threshold: int = 5) -> bool` — `True` when `unprocessed_count >= n_threshold`.
  - `mark_ready(store_dir: str, plugin: str) -> str` — writes a `<plugin>.ready` marker file next to the store; returns its path. (Phase B will consume + clear these markers; Phase A only sets them.)

- [ ] **Step 1: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_batch.py`:

```python
import os
import tempfile
import unittest
from evidence import EvidenceRecord, append_evidence
from batch import unprocessed_count, should_run_batch, mark_ready


def er(i, processed=False):
    r = EvidenceRecord("s%d" % i, "p", "usage", [], {}, "t", "/t")
    r.processed = processed
    return r


class TestBatch(unittest.TestCase):
    def test_unprocessed_count(self):
        with tempfile.TemporaryDirectory() as d:
            append_evidence(d, er(1))
            append_evidence(d, er(2, processed=True))
            append_evidence(d, er(3))
            self.assertEqual(unprocessed_count(d, "p"), 2)

    def test_should_run_batch_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5):
                append_evidence(d, er(i))
            self.assertFalse(should_run_batch(d, "p", n_threshold=6))
            self.assertTrue(should_run_batch(d, "p", n_threshold=5))

    def test_mark_ready_writes_marker(self):
        with tempfile.TemporaryDirectory() as d:
            path = mark_ready(d, "p")
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith("p.ready"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_batch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'batch'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/talon-plugin-manager/distill/batch.py`:

```python
"""Decide when a plugin's accumulated evidence is ready for a (Phase B) distill pass."""
from __future__ import annotations
import os

from evidence import read_evidence


def unprocessed_count(store_dir: str, plugin: str) -> int:
    return sum(1 for r in read_evidence(store_dir, plugin) if not r.get("processed", False))


def should_run_batch(store_dir: str, plugin: str, n_threshold: int = 5) -> bool:
    return unprocessed_count(store_dir, plugin) >= n_threshold


def mark_ready(store_dir: str, plugin: str) -> str:
    os.makedirs(store_dir, exist_ok=True)
    path = os.path.join(store_dir, f"{plugin}.ready")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("ready\n")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_batch.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/talon-plugin-manager/distill/batch.py plugins/talon-plugin-manager/distill/test_batch.py
git commit -m "feat(distill): batch-threshold checker and ready marker"
```

---

## Task 8: Capture CLI + SessionEnd hook wiring

**Files:**
- Create: `plugins/talon-plugin-manager/distill/capture.py`
- Create: `plugins/talon-plugin-manager/hooks/hooks.json`
- Test: `plugins/talon-plugin-manager/distill/test_capture.py`

**Interfaces:**
- Consumes: every module above. Reads the hook payload JSON from stdin: `{"session_id","transcript_path","cwd","hook_event_name"}`.
- Produces:
  - `run_capture(payload: dict, store_dir: str, installed_plugins_path: str, n_threshold: int = 5) -> list[str]` — does the full pipeline (registry → parse → detect usage + under-trigger → friction → append one `EvidenceRecord` per affected plugin → set `.ready` marker if threshold crossed) and returns the list of plugins it wrote evidence for. Pure function (no stdin), so it is unit-testable.
  - `main()` — reads stdin JSON, calls `run_capture` with defaults, exits `0` always (a hook must never block session end).

- [ ] **Step 1: Confirm the plugin hooks schema**

Before writing `hooks.json`, confirm the current Claude Code *plugin* hooks format and the `SessionEnd` stdin fields. Use the `claude-code-guide` agent or fetch the docs:

Run (one option): ask `claude-code-guide`: "What is the exact hooks.json format for a Claude Code plugin, and what JSON fields does a SessionEnd hook receive on stdin? Does plugin.json need a `hooks` key or is hooks/hooks.json auto-loaded? Is `${CLAUDE_PLUGIN_ROOT}` the right variable?"
Expected: confirms a top-level `{"hooks": {"SessionEnd": [{"hooks": [{"type":"command","command":...}]}]}}` structure (adjust Step 4 if it differs), that stdin includes `session_id`/`transcript_path`/`cwd`/`hook_event_name`, and that `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin dir.

- [ ] **Step 2: Write the failing test**

Create `plugins/talon-plugin-manager/distill/test_capture.py`:

```python
import os
import tempfile
import unittest
from capture import run_capture

HERE = os.path.dirname(__file__)
FIXDIR = os.path.join(HERE, "fixtures")
USAGE = os.path.join(FIXDIR, "transcript_usage.jsonl")
UNDER = os.path.join(FIXDIR, "transcript_under_trigger.jsonl")


def installed_with(tmp, mapping):
    # mapping: plugin -> install_path; write a minimal installed_plugins.json
    import json
    p = os.path.join(tmp, "installed.json")
    plugins = {f"{name}@talon": [{"installPath": path}] for name, path in mapping.items()}
    json.dump({"version": 2, "plugins": plugins}, open(p, "w"))
    return p


class TestCapture(unittest.TestCase):
    def test_records_usage(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"talon-plugin-manager": ""})
            payload = {"session_id": "s1", "transcript_path": USAGE, "cwd": "/x", "hook_event_name": "SessionEnd"}
            wrote = run_capture(payload, store, ip)
            self.assertIn("talon-plugin-manager", wrote)
            from evidence import read_evidence
            rows = read_evidence(store, "talon-plugin-manager")
            self.assertEqual(rows[0]["kind"], "usage")
            self.assertTrue(rows[0]["friction"]["has_tool_errors"])  # USAGE fixture has a failed bash

    def test_records_under_trigger(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"terraform-module-steering": FIXDIR})  # distill.json in fixtures/
            payload = {"session_id": "s2", "transcript_path": UNDER, "cwd": "/x", "hook_event_name": "SessionEnd"}
            wrote = run_capture(payload, store, ip)
            self.assertEqual(wrote, ["terraform-module-steering"])
            from evidence import read_evidence
            self.assertEqual(read_evidence(store, "terraform-module-steering")[0]["kind"], "under_trigger")

    def test_no_talon_activity_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"some-other": ""})
            payload = {"session_id": "s3", "transcript_path": UNDER, "cwd": "/x", "hook_event_name": "SessionEnd"}
            self.assertEqual(run_capture(payload, store, ip), [])

    def test_threshold_sets_ready_marker(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"talon-plugin-manager": ""})
            payload = {"session_id": "s", "transcript_path": USAGE, "cwd": "/x", "hook_event_name": "SessionEnd"}
            for _ in range(5):
                run_capture(payload, store, ip, n_threshold=5)
            self.assertTrue(os.path.exists(os.path.join(store, "talon-plugin-manager.ready")))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_capture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'capture'`.

- [ ] **Step 4: Write the capture CLI**

Create `plugins/talon-plugin-manager/distill/capture.py`:

```python
#!/usr/bin/env python3
"""SessionEnd capture: append deterministic distillation evidence for any Talon
plugin used (or under-triggered) in the just-ended session. No LLM, no network."""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

from registry import load_talon_registry
from transcript import parse_transcript
from detect import detect_usage, load_domain_map, under_triggered
from friction import scan_friction
from evidence import EVIDENCE_DIR, EvidenceRecord, append_evidence
from batch import should_run_batch, mark_ready

DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")


def run_capture(payload: dict, store_dir: str, installed_plugins_path: str, n_threshold: int = 5) -> list[str]:
    registry = load_talon_registry(installed_plugins_path)
    if not registry:
        return []
    parsed = parse_transcript(payload.get("transcript_path", ""))
    names = set(registry)
    used = detect_usage(parsed.tool_calls, names)
    domain_map = load_domain_map(registry)
    under = under_triggered(parsed.tool_calls, names, domain_map)
    if not used and not under:
        return []
    friction = scan_friction(parsed.tool_calls, parsed.user_texts).as_dict()
    captured_at = datetime.now(timezone.utc).isoformat()
    wrote: list[str] = []
    for plugin in sorted(used | under):
        rec = EvidenceRecord(
            session_id=payload.get("session_id", ""),
            plugin=plugin,
            kind="usage" if plugin in used else "under_trigger",
            skills_used=sorted(used & {plugin}),
            friction=friction,
            captured_at=captured_at,
            transcript_path=payload.get("transcript_path", ""),
        )
        append_evidence(store_dir, rec)
        wrote.append(plugin)
        if should_run_batch(store_dir, plugin, n_threshold):
            mark_ready(store_dir, plugin)
    return wrote


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # never block session end
    try:
        run_capture(payload, EVIDENCE_DIR, DEFAULT_INSTALLED)
    except Exception:
        return 0  # capture is best-effort; never raise into the hook
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p test_capture.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Write the hook manifest**

Create `plugins/talon-plugin-manager/hooks/hooks.json` (adjust to the schema confirmed in Step 1):

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/distill/capture.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 7: End-to-end smoke test of the CLI**

Run (feeds the usage fixture through the real stdin path, into a temp store):

```bash
python3 - <<'PY'
import json, os, tempfile, subprocess, sys
here = "plugins/talon-plugin-manager/distill"
fix = os.path.join(here, "fixtures", "transcript_usage.jsonl")
with tempfile.TemporaryDirectory() as d:
    ip = os.path.join(d, "ip.json")
    json.dump({"version":2,"plugins":{"talon-plugin-manager@talon":[{"installPath":""}]}}, open(ip,"w"))
    env = dict(os.environ)
    payload = {"session_id":"smoke","transcript_path":fix,"cwd":"/x","hook_event_name":"SessionEnd"}
    # call run_capture directly to assert disk write into a temp store
    sys.path.insert(0, here)
    from capture import run_capture
    store = os.path.join(d, "store")
    wrote = run_capture(payload, store, ip)
    assert wrote == ["talon-plugin-manager"], wrote
    assert os.path.exists(os.path.join(store, "talon-plugin-manager.jsonl"))
    print("SMOKE OK:", wrote)
PY
```
Expected: prints `SMOKE OK: ['talon-plugin-manager']`.

- [ ] **Step 8: Run the full suite + validator**

Run: `python3 -m unittest discover -s plugins/talon-plugin-manager/distill -p 'test_*.py' -v`
Expected: PASS (all tests, ~30).
Run: `python3 plugins/talon-plugin-manager/skills/onboard-plugin/scripts/validate_talon.py --root .`
Expected: exits `0`, no `ERROR:` lines.

- [ ] **Step 9: Commit**

```bash
git add plugins/talon-plugin-manager/distill/capture.py plugins/talon-plugin-manager/distill/test_capture.py plugins/talon-plugin-manager/hooks/hooks.json
git commit -m "feat(distill): SessionEnd capture CLI + plugin hook wiring"
```

---

## Self-Review

**Spec coverage (Phase A + packaging sections of the design):**
- §1 Packaging rename → Task 1. ✓ (Skill name stays `onboard-plugin`; major bump 2.0.0; both catalogs + both manifests; validator gate.)
- §2 Phase A capture: read hook stdin → Task 8; load `@talon` registry → Task 2; parse transcript → Task 3; usage + under-trigger detection → Task 4; friction pre-scan → Task 5; evidence record → Task 6; threshold + ready marker → Tasks 7–8. ✓
- §5 Domain-signal map (self-declared `distill.json`) → Task 4 `load_domain_map`. ✓ (LLM-inferred fallback is Phase B — out of scope, noted.)
- §6 Batch trigger & state (evidence store path, threshold, ready marker, `processed` flag) → Tasks 6–8. ✓ (Headless `claude -p` spawn is Phase B — Phase A only sets the marker, as designed.)

**Deferred to Plan 2 (Distill, Phase B), intentionally not here:** trajectory builder, abstraction-first reflection, 4-way decision, skill-vs-agent-vs-environment classification, redaction layers L1–L3, fingerprint/dedup, `gh` issue emit, skill-creator handoff, the `distill-plugin` SKILL.md, and the auto-spawn of the batch pass. Phase A's only obligation to Phase B is a well-formed evidence store + `.ready` markers, which Tasks 6–8 produce.

**Placeholder scan:** No `TBD`/`handle edge cases`/"write tests for the above" — every step has concrete code and an exact run command with expected output. ✓

**Type consistency:** `ToolCall` / `ParsedTranscript` (Task 3) are consumed with the same field names in Tasks 4–5; `EvidenceRecord` field order (Task 6) matches its positional construction in Tasks 7–8 tests; `FrictionHints.as_dict()` (Task 5) feeds `EvidenceRecord.friction` (Task 6); `load_talon_registry -> dict[name,path]` (Task 2) is consumed as `set(registry)` + `load_domain_map(registry)` (Tasks 4, 8). ✓

**Known risk:** the exact plugin `hooks.json` schema and `SessionEnd` stdin fields are confirmed at execution time (Task 8 Step 1) rather than assumed; the CLI is written as a testable pure function (`run_capture`) so its logic is verified independently of the hook wiring.
