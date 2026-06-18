import json
import os
import tempfile
import unittest
from quarantine import quarantine


class TestQuarantine(unittest.TestCase):
    def test_writes_finding_and_reason(self):
        with tempfile.TemporaryDirectory() as d:
            path = quarantine({"plugin": "p", "title": "x"}, "secret-scan-blocked", d)
            self.assertTrue(os.path.exists(path))
            data = json.load(open(path))
            self.assertEqual(data["reason"], "secret-scan-blocked")
            self.assertEqual(data["finding"]["plugin"], "p")

    def test_creates_dir(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "q")
            path = quarantine({"plugin": "p"}, "r", sub)
            self.assertTrue(path.startswith(sub))
