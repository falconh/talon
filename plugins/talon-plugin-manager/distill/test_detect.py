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
        self.assertEqual(load_domain_map({"x": "/no/such/dir"}), {})
