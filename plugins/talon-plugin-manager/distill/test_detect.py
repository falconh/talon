import os
import unittest
from transcript import parse_transcript, ToolCall
from detect import detect_usage, detect_domain, under_triggered, load_domain_map, domain_match_seqs

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
        # domain activity AND an actual Skill call for the plugin => not under-triggered
        calls = parse_transcript(UNDER).tool_calls
        calls.append(ToolCall(id="s", name="Skill",
                              input={"skill": "terraform-module-steering:terraform-module-steering"}))
        self.assertEqual(under_triggered(calls, {"terraform-module-steering"}, DMAP), set())

    def test_load_domain_map_reads_distill_json(self):
        reg = {"terraform-module-steering": FIXDIR}  # distill.json lives in fixtures/
        dmap = load_domain_map(reg)
        self.assertEqual(dmap["terraform-module-steering"]["cmds"], ["terraform", "tofu"])
        self.assertEqual(dmap["terraform-module-steering"]["globs"], ["**/*.tf"])

    def test_load_domain_map_skips_missing(self):
        self.assertEqual(load_domain_map({"x": "/no/such/dir"}, inferred_dir="/no/such/dir"), {})

    def test_load_domain_map_uses_cached_inference_when_undeclared(self):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as inferred:
            with open(os.path.join(inferred, "tms.json"), "w") as fh:
                _json.dump({"domain_globs": ["**/*.tf"], "domain_cmds": ["terraform"]}, fh)
            # registry plugin has NO install distill.json, but a cached inferred one exists
            dmap = load_domain_map({"tms": "/no/such/dir"}, inferred_dir=inferred)
            self.assertEqual(dmap["tms"]["cmds"], ["terraform"])

    def test_declared_distill_json_wins_over_inferred(self):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as inferred:
            with open(os.path.join(inferred, "terraform-module-steering.json"), "w") as fh:
                _json.dump({"domain_globs": ["**/*.bogus"], "domain_cmds": ["bogus"]}, fh)
            dmap = load_domain_map({"terraform-module-steering": FIXDIR}, inferred_dir=inferred)
            self.assertEqual(dmap["terraform-module-steering"]["cmds"], ["terraform", "tofu"])

    def test_glob_matches_nested_and_bare_paths(self):
        from detect import _glob_match
        self.assertTrue(_glob_match("infra/main.tf", "**/*.tf"))
        self.assertTrue(_glob_match("main.tf", "**/*.tf"))           # ** matches zero dirs
        self.assertTrue(_glob_match("a/b/c/x.tf", "**/*.tf"))
        self.assertFalse(_glob_match("infra/main.tfvars", "**/*.tf"))
        self.assertFalse(_glob_match("a/main.tf", "*.tf"))           # * is single-segment

    def test_detect_domain_matches_nested_tf_write(self):
        from transcript import ToolCall
        calls = [ToolCall("w", "Write", {"file_path": "envs/prod/modules/vpc/main.tf"})]
        self.assertEqual(detect_domain(calls, DMAP), {"terraform-module-steering"})

    def test_domain_match_seqs_returns_matching_call_seqs(self):
        calls = [
            ToolCall("a", "Write", {"file_path": "infra/main.tf"}, seq=0),
            ToolCall("b", "Bash", {"command": "terraform init"}, seq=1),
            ToolCall("c", "Bash", {"command": "ls -la"}, seq=2),
            ToolCall("d", "Read", {"file_path": "README.md"}, seq=3),
        ]
        sig = {"globs": ["**/*.tf"], "cmds": ["terraform", "tofu"]}
        self.assertEqual(domain_match_seqs(calls, sig), [0, 1])
