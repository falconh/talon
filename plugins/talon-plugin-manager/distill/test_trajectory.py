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
