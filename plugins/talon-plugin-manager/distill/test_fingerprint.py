import unittest
from fingerprint import finding_fingerprint, marker, extract_fp


class TestFingerprint(unittest.TestCase):
    def test_stable_across_whitespace_and_case(self):
        a = finding_fingerprint("p", "improve_skill", "Missing remote-source guidance")
        b = finding_fingerprint("p", "improve_skill", "  missing   REMOTE-source guidance ")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)

    def test_decision_changes_fingerprint(self):
        a = finding_fingerprint("p", "improve_skill", "x")
        b = finding_fingerprint("p", "optimize_description", "x")
        self.assertNotEqual(a, b)

    def test_marker_roundtrip(self):
        fp = finding_fingerprint("p", "skip", "y")
        self.assertEqual(extract_fp("body\n" + marker(fp) + "\n"), fp)

    def test_extract_none_when_absent(self):
        self.assertIsNone(extract_fp("no marker here"))
