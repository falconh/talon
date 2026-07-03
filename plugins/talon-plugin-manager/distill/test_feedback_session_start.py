"""The SessionStart directive hook must emit the watch-for-dissatisfaction priming text."""
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "feedback-session-start.sh")
SH = shutil.which("sh") or "/bin/sh"


class TestSessionStartDirective(unittest.TestCase):
    def test_emits_directive(self):
        p = subprocess.run([SH, HOOK], input=b"{}", capture_output=True)
        self.assertEqual(p.returncode, 0)
        out = p.stdout.decode()
        self.assertIn("skill-feedback", out)
        self.assertIn("dissatisf", out.lower())
        self.assertIn("do not interrupt", out.lower().replace("\n", " "))
        self.assertIn("user", out.lower())


if __name__ == "__main__":
    unittest.main()
