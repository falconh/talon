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
