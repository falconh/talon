"""End-to-end integration test of the distill pass machinery the skill drives:
seed store -> build packet -> emit (open / quarantine) -> close out. No network:
gh is a fake runner; the store/quarantine/inferred dirs are temp."""
import json
import os
import tempfile
import unittest

from evidence import EvidenceRecord, append_evidence, read_evidence
from batch import mark_ready
from distill_pass import build_packet
from emit import emit_finding
from pass_state import ready_plugins
import distill_pass

FRICTION = {"has_tool_errors": True, "repeated_error_count": 2, "retry": True}


class FakeGh:
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:3] == ["gh", "issue", "list"]:
            return 0, "[]", ""
        if args[:3] == ["gh", "issue", "create"]:
            return 0, "https://github.com/falconh/talon/issues/1\n", ""
        return 0, "", ""

    def created(self):
        return [a for a in self.calls if a[:3] == ["gh", "issue", "create"]]


def make_install(tmp):
    os.makedirs(os.path.join(tmp, ".claude-plugin"))
    with open(os.path.join(tmp, ".claude-plugin", "plugin.json"), "w") as fh:
        json.dump({"name": "onboard-plugin", "repository": "https://github.com/falconh/talon"}, fh)
    return tmp


class TestPipelineE2E(unittest.TestCase):
    def test_full_pass_opens_clean_quarantines_dirty_and_closes(self):
        with tempfile.TemporaryDirectory() as store, \
             tempfile.TemporaryDirectory() as inst, \
             tempfile.TemporaryDirectory() as quar:
            make_install(inst)
            for i in range(3):
                append_evidence(store, EvidenceRecord(
                    f"s{i}", "onboard-plugin", "usage", ["onboard-plugin"],
                    FRICTION, "2026-06-17T00:00:00Z", "/dev/null"))
            mark_ready(store, "onboard-plugin")

            # 1) packet: one ready plugin, repo resolved, 3 unprocessed sessions
            packet = build_packet(store, {"onboard-plugin": inst})
            entry = packet["plugins"][0]
            self.assertEqual(entry["repo"], "falconh/talon")
            self.assertEqual(entry["unprocessed"], 3)

            gh = FakeGh()

            # 2a) a clean finding -> opened, with fingerprint marker in the body
            clean = {"repo": entry["repo"], "plugin": "onboard-plugin", "decision": "improve_skill",
                     "anchor": "remote-source guidance missing", "title": "[distill] clarify remote sources",
                     "body": "The skill should explain the HTTPS url source vs the github shorthand."}
            res_clean = emit_finding(clean, runner=gh, quarantine_dir=quar)
            self.assertEqual(res_clean["status"], "opened")

            # 2b) a dirty finding (leaked key) -> quarantined, never posted
            dirty = {**clean, "anchor": "another gap",
                     "body": "it printed AKIA1234567890ABCD12 while failing"}
            res_dirty = emit_finding(dirty, runner=gh, quarantine_dir=quar)
            self.assertEqual(res_dirty["status"], "quarantined")

            # exactly one issue was created (the clean one); the dirty one was blocked
            self.assertEqual(len(gh.created()), 1)
            self.assertEqual(len(os.listdir(quar)), 1)

            # 3) close out -> processed, compacted, ready cleared
            distill_pass.main(["close", store, "onboard-plugin", "s0,s1,s2"])
            self.assertEqual(ready_plugins(store), [])
            self.assertEqual(read_evidence(store, "onboard-plugin"), [])  # compacted away
