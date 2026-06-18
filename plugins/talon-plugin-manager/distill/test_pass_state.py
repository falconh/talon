import os
import tempfile
import unittest
from evidence import EvidenceRecord, append_evidence, read_evidence
from batch import mark_ready
from pass_state import ready_plugins, mark_processed, clear_ready


def rec(sid):
    return EvidenceRecord(sid, "p", "usage", [], {}, "t", "/t")


class TestPassState(unittest.TestCase):
    def test_ready_plugins_lists_markers(self):
        with tempfile.TemporaryDirectory() as d:
            mark_ready(d, "p")
            mark_ready(d, "q")
            self.assertEqual(ready_plugins(d), ["p", "q"])

    def test_clear_ready_removes_marker(self):
        with tempfile.TemporaryDirectory() as d:
            mark_ready(d, "p")
            clear_ready(d, "p")
            self.assertEqual(ready_plugins(d), [])

    def test_mark_processed_flips_named_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            append_evidence(d, rec("s1"))
            append_evidence(d, rec("s2"))
            changed = mark_processed(d, "p", ["s1"])
            self.assertEqual(changed, 1)
            rows = {r["session_id"]: r["processed"] for r in read_evidence(d, "p")}
            self.assertTrue(rows["s1"])
            self.assertFalse(rows["s2"])

    def test_mark_processed_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            append_evidence(d, rec("s1"))
            mark_processed(d, "p", ["s1"])
            self.assertEqual(mark_processed(d, "p", ["s1"]), 0)
