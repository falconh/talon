import os
import unittest
from registry import load_talon_registry

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "installed_plugins.json")


class TestRegistry(unittest.TestCase):
    def test_only_talon_plugins(self):
        reg = load_talon_registry(FIX)
        self.assertEqual(set(reg), {"plugin-manager", "terraform-module-steering"})

    def test_maps_name_to_install_path(self):
        reg = load_talon_registry(FIX)
        self.assertEqual(reg["terraform-module-steering"], "/x/tms/1.1.0")

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_talon_registry("/no/such/file.json"), {})


class TestResolveRepo(unittest.TestCase):
    def test_resolve_repo_from_manifest(self):
        import json
        import tempfile
        from registry import resolve_repo
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude-plugin"))
            with open(os.path.join(d, ".claude-plugin", "plugin.json"), "w") as fh:
                json.dump({"repository": "https://github.com/falconh/talon.git"}, fh)
            self.assertEqual(resolve_repo(d), "falconh/talon")

    def test_resolve_repo_empty_or_missing(self):
        from registry import resolve_repo
        self.assertIsNone(resolve_repo(""))
        self.assertIsNone(resolve_repo("/no/such/dir"))
