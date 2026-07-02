"""Tests for the TALON_DISTILL_HOME override (paths.py) that lets evals run
against a throwaway tree instead of the user's real evidence store."""
import os
import unittest

import paths


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


class TestInstalledOverride(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("TALON_DISTILL_INSTALLED")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("TALON_DISTILL_INSTALLED", None)
        else:
            os.environ["TALON_DISTILL_INSTALLED"] = self._saved

    def test_default_registry_path_when_unset(self):
        os.environ.pop("TALON_DISTILL_INSTALLED", None)
        self.assertEqual(paths.installed_plugins(),
                         os.path.expanduser("~/.claude/plugins/installed_plugins.json"))

    def test_env_overrides_registry_path(self):
        os.environ["TALON_DISTILL_INSTALLED"] = "/tmp/fake/installed_plugins.json"
        self.assertEqual(paths.installed_plugins(), "/tmp/fake/installed_plugins.json")


if __name__ == "__main__":
    unittest.main()
