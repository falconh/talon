import os
import tempfile
import unittest
from capture import run_capture

HERE = os.path.dirname(__file__)
FIXDIR = os.path.join(HERE, "fixtures")
USAGE = os.path.join(FIXDIR, "transcript_usage.jsonl")
UNDER = os.path.join(FIXDIR, "transcript_under_trigger.jsonl")
BLEED = os.path.join(FIXDIR, "transcript_friction_bleed.jsonl")


def installed_with(tmp, mapping):
    # mapping: plugin -> install_path; write a minimal installed_plugins.json
    import json
    p = os.path.join(tmp, "installed.json")
    plugins = {f"{name}@talon": [{"installPath": path}] for name, path in mapping.items()}
    with open(p, "w") as fh:
        json.dump({"version": 2, "plugins": plugins}, fh)
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

    def test_records_repo_and_skill_ids(self):
        import json as _json
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            inst = os.path.join(d, "inst")
            os.makedirs(os.path.join(inst, ".claude-plugin"))
            with open(os.path.join(inst, ".claude-plugin", "plugin.json"), "w") as fh:
                _json.dump({"repository": "https://github.com/falconh/talon"}, fh)
            ip = installed_with(d, {"talon-plugin-manager": inst})
            payload = {"session_id": "s", "transcript_path": USAGE, "cwd": "/x", "hook_event_name": "SessionEnd"}
            run_capture(payload, store, ip)
            from evidence import read_evidence
            rec = read_evidence(store, "talon-plugin-manager")[0]
            self.assertEqual(rec["repo"], "falconh/talon")                       # captured at capture time
            self.assertEqual(rec["skills_used"], ["talon-plugin-manager:onboard-plugin"])  # real skill id

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

    def test_threshold_sets_ready_marker(self):
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "store")
            ip = installed_with(d, {"talon-plugin-manager": ""})
            payload = {"session_id": "s", "transcript_path": USAGE, "cwd": "/x", "hook_event_name": "SessionEnd"}
            for _ in range(5):
                run_capture(payload, store, ip, n_threshold=5)
            self.assertTrue(os.path.exists(os.path.join(store, "talon-plugin-manager.ready")))
