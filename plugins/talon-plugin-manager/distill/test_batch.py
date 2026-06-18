import os
import tempfile
import unittest
from evidence import EvidenceRecord, append_evidence
from batch import unprocessed_count, should_run_batch, mark_ready


def er(i, processed=False):
    r = EvidenceRecord("s%d" % i, "p", "usage", [], {}, "t", "/t")
    r.processed = processed
    return r


class TestBatch(unittest.TestCase):
    def test_unprocessed_count(self):
        with tempfile.TemporaryDirectory() as d:
            append_evidence(d, er(1))
            append_evidence(d, er(2, processed=True))
            append_evidence(d, er(3))
            self.assertEqual(unprocessed_count(d, "p"), 2)

    def test_should_run_batch_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5):
                append_evidence(d, er(i))
            self.assertFalse(should_run_batch(d, "p", n_threshold=6))
            self.assertTrue(should_run_batch(d, "p", n_threshold=5))

    def test_mark_ready_writes_marker(self):
        with tempfile.TemporaryDirectory() as d:
            path = mark_ready(d, "p")
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith("p.ready"))
