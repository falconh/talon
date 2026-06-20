import json
import os
import tempfile
import unittest
from evidence import EvidenceRecord, append_evidence
from batch import mark_ready
from pass_state import mark_processed
from distill_pass import resolve_repo, build_packet

HERE = os.path.dirname(__file__)
USAGE = os.path.join(HERE, "fixtures", "transcript_usage.jsonl")


def make_install(tmp, repository=None, with_distill=False):
    """Create a fake plugin install dir with a manifest (+ optional distill.json)."""
    os.makedirs(os.path.join(tmp, ".claude-plugin"))
    manifest = {"name": "p"}
    if repository:
        manifest["repository"] = repository
    with open(os.path.join(tmp, ".claude-plugin", "plugin.json"), "w") as fh:
        json.dump(manifest, fh)
    if with_distill:
        with open(os.path.join(tmp, "distill.json"), "w") as fh:
            json.dump({"domain_globs": ["**/*.tf"], "domain_cmds": ["terraform"]}, fh)
    return tmp


def ev(sid, kind="usage"):
    return EvidenceRecord(sid, "p", kind, [], {"has_tool_errors": True}, "t", USAGE)


class TestResolveRepo(unittest.TestCase):
    def test_parses_github_repository(self):
        with tempfile.TemporaryDirectory() as d:
            make_install(d, repository="https://github.com/falconh/talon")
            self.assertEqual(resolve_repo(d), "falconh/talon")

    def test_strips_git_suffix(self):
        with tempfile.TemporaryDirectory() as d:
            make_install(d, repository="https://github.com/falconh/talon.git")
            self.assertEqual(resolve_repo(d), "falconh/talon")

    def test_none_when_no_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(resolve_repo(d))


class TestBuildPacket(unittest.TestCase):
    def test_packet_has_ready_plugin_with_trajectories_and_repo(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as inst:
            make_install(inst, repository="https://github.com/falconh/talon", with_distill=True)
            append_evidence(store, ev("s1"))
            append_evidence(store, ev("s2"))
            mark_ready(store, "p")
            packet = build_packet(store, {"p": inst})
            self.assertEqual(len(packet["plugins"]), 1)
            entry = packet["plugins"][0]
            self.assertEqual(entry["repo"], "falconh/talon")
            self.assertTrue(entry["domain_declared"])
            self.assertEqual(entry["unprocessed"], 2)
            self.assertEqual(len(entry["sessions"]), 2)
            self.assertIn("Skill talon-plugin-manager:onboard-plugin", entry["sessions"][0]["trajectory"])

    def test_packet_excludes_processed(self):
        with tempfile.TemporaryDirectory() as store:
            append_evidence(store, ev("s1"))
            append_evidence(store, ev("s2"))
            mark_ready(store, "p")
            mark_processed(store, "p", ["s1"])
            packet = build_packet(store, {"p": ""})
            self.assertEqual(packet["plugins"][0]["unprocessed"], 1)
            self.assertEqual(packet["plugins"][0]["sessions"][0]["session_id"], "s2")

    def test_packet_empty_when_no_ready(self):
        with tempfile.TemporaryDirectory() as store:
            append_evidence(store, ev("s1"))  # no ready marker
            self.assertEqual(build_packet(store, {"p": ""})["plugins"], [])

    def test_packet_repo_prefers_recorded(self):
        with tempfile.TemporaryDirectory() as store:
            rec = EvidenceRecord("s1", "p", "usage", [], {}, "t", USAGE)
            rec.repo = "owner/recorded"
            append_evidence(store, rec)
            mark_ready(store, "p")
            packet = build_packet(store, {"p": "/no/install/path"})  # registry miss
            self.assertEqual(packet["plugins"][0]["repo"], "owner/recorded")

    def test_packet_repo_reverse_lookup_by_skill(self):
        # plugin name not installed (rename), but a used skill maps to an installed plugin's dir
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as inst:
            os.makedirs(os.path.join(inst, ".claude-plugin"))
            os.makedirs(os.path.join(inst, "skills", "onboard-plugin"))
            with open(os.path.join(inst, ".claude-plugin", "plugin.json"), "w") as fh:
                json.dump({"repository": "https://github.com/falconh/talon"}, fh)
            rec = EvidenceRecord("s1", "talon-plugin-manager", "usage",
                                 ["talon-plugin-manager:onboard-plugin"], {}, "t", USAGE)
            append_evidence(store, rec)
            mark_ready(store, "talon-plugin-manager")
            registry = {"talon-plugin-manager": "", "talon-onboarding": inst}  # renamed name absent
            packet = build_packet(store, registry)
            self.assertEqual(packet["plugins"][0]["repo"], "falconh/talon")
