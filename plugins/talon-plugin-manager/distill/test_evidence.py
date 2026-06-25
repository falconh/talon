import json
import os
import tempfile
import unittest
from evidence import (EvidenceRecord, append_evidence, read_evidence,
                      upsert_evidence, dedupe_evidence)


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

    def test_upsert_replaces_unprocessed_same_session(self):
        with tempfile.TemporaryDirectory() as d:
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", [],
                            {"has_tool_errors": False}, "2026-06-22T00:00:00Z", "/t"))
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", ["x"],
                            {"has_tool_errors": True}, "2026-06-24T00:00:00Z", "/t"))
            rows = read_evidence(d, "p")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["captured_at"], "2026-06-24T00:00:00Z")
            self.assertTrue(rows[0]["friction"]["has_tool_errors"])

    def test_upsert_keeps_distinct_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", [], {}, "t", "/t"))
            upsert_evidence(d, EvidenceRecord("s2", "p", "usage", [], {}, "t", "/t"))
            self.assertEqual(len(read_evidence(d, "p")), 2)

    def test_upsert_skips_when_already_processed(self):
        with tempfile.TemporaryDirectory() as d:
            seed = EvidenceRecord("s1", "p", "usage", [], {}, "2026-06-22T00:00:00Z", "/t")
            seed.processed = True
            append_evidence(d, seed)
            upsert_evidence(d, EvidenceRecord("s1", "p", "usage", [],
                            {"has_tool_errors": True}, "2026-06-24T00:00:00Z", "/t"))
            rows = read_evidence(d, "p")
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["processed"])
            self.assertEqual(rows[0]["captured_at"], "2026-06-22T00:00:00Z")

    def test_dedupe_prefers_processed_then_newest(self):
        rows = [
            {"session_id": "s1", "captured_at": "2026-06-22T00:00:00Z", "processed": False},
            {"session_id": "s1", "captured_at": "2026-06-24T00:00:00Z", "processed": False},
            {"session_id": "s2", "captured_at": "2026-06-20T00:00:00Z", "processed": True},
            {"session_id": "s2", "captured_at": "2026-06-21T00:00:00Z", "processed": False},
        ]
        out = dedupe_evidence(rows)
        self.assertEqual(len(out), 2)
        by = {r["session_id"]: r for r in out}
        self.assertEqual(by["s1"]["captured_at"], "2026-06-24T00:00:00Z")
        self.assertTrue(by["s2"]["processed"])
