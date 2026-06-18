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
