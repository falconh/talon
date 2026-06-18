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
