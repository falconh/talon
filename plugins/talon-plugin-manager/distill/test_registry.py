import os
import unittest
from registry import load_talon_registry

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "installed_plugins.json")


class TestRegistry(unittest.TestCase):
    def test_only_talon_plugins(self):
        reg = load_talon_registry(FIX)
        self.assertEqual(set(reg), {"talon-plugin-manager", "terraform-module-steering"})

    def test_maps_name_to_install_path(self):
        reg = load_talon_registry(FIX)
        self.assertEqual(reg["terraform-module-steering"], "/x/tms/1.1.0")

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_talon_registry("/no/such/file.json"), {})
