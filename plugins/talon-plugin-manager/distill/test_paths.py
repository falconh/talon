"""Tests for the TALON_DISTILL_HOME override (paths.py) that lets evals and the
auto-pass run against a throwaway tree instead of the user's real evidence store."""
import os
import subprocess
import sys
import tempfile
import unittest

import paths

HERE = os.path.dirname(os.path.abspath(__file__))


class TestPaths(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("TALON_DISTILL_HOME")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("TALON_DISTILL_HOME", None)
        else:
            os.environ["TALON_DISTILL_HOME"] = self._saved

    def test_default_home_when_unset(self):
        os.environ.pop("TALON_DISTILL_HOME", None)
        self.assertEqual(paths.home(), os.path.expanduser("~/.claude/talon-distill"))

    def test_empty_env_falls_back_to_default(self):
        os.environ["TALON_DISTILL_HOME"] = ""  # set-but-empty must not yield "/evidence"
        self.assertEqual(paths.home(), os.path.expanduser("~/.claude/talon-distill"))

    def test_env_overrides_home_and_subpaths(self):
        os.environ["TALON_DISTILL_HOME"] = "/tmp/distill-xyz"
        self.assertEqual(paths.home(), "/tmp/distill-xyz")
        self.assertEqual(paths.under("evidence"), "/tmp/distill-xyz/evidence")
        self.assertEqual(paths.under("pending", "p.log"), "/tmp/distill-xyz/pending/p.log")

    def test_env_expands_user(self):
        os.environ["TALON_DISTILL_HOME"] = "~/somewhere-distill"
        self.assertEqual(paths.home(), os.path.expanduser("~/somewhere-distill"))


class TestStoreOverrideEndToEnd(unittest.TestCase):
    """A subprocess (the real eval entrypoint) that exports TALON_DISTILL_HOME must
    resolve the default store to the override — never the user's real ~/.claude store."""

    def _run(self, args, home):
        env = dict(os.environ, TALON_DISTILL_HOME=home)
        return subprocess.run([sys.executable, *args], cwd=HERE, env=env,
                              capture_output=True, text=True)

    def test_status_reads_env_pointed_store_without_explicit_arg(self):
        with tempfile.TemporaryDirectory() as home:
            seed = os.path.join(HERE, "..", "skills", "distill-plugin", "evals", "seed_store.py")
            store = os.path.join(home, "evidence")
            seeded = self._run([seed, store], home)
            self.assertEqual(seeded.returncode, 0, seeded.stderr)

            # status with NO store arg must fall back to the env-pointed EVIDENCE_DIR
            res = self._run(["distill_pass.py", "status"], home)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("talon-plugin-manager", res.stdout)
            self.assertIn("terraform-module-steering", res.stdout)


if __name__ == "__main__":
    unittest.main()
