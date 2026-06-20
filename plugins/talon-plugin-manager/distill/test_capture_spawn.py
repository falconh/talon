import os
import tempfile
import unittest
import capture
from capture import run_capture, _spawn_env, _spawn_command

HERE = os.path.dirname(__file__)
USAGE = os.path.join(HERE, "fixtures", "transcript_usage.jsonl")


def installed_with(tmp, mapping):
    import json
    p = os.path.join(tmp, "installed.json")
    plugins = {f"{n}@talon": [{"installPath": path}] for n, path in mapping.items()}
    with open(p, "w") as fh:
        json.dump({"version": 2, "plugins": plugins}, fh)
    return p


class TestCaptureSpawn(unittest.TestCase):
    def _payload(self):
        return {"session_id": "s", "transcript_path": USAGE, "cwd": "/x", "hook_event_name": "SessionEnd"}

    def test_spawner_called_when_threshold_crossed(self):
        with tempfile.TemporaryDirectory() as d:
            store, ip = os.path.join(d, "store"), installed_with(d, {"talon-plugin-manager": ""})
            calls = []
            for _ in range(5):
                run_capture(self._payload(), store, ip, n_threshold=5, spawner=calls.append)
            self.assertIn("talon-plugin-manager", calls)

    def test_spawner_not_called_before_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            store, ip = os.path.join(d, "store"), installed_with(d, {"talon-plugin-manager": ""})
            calls = []
            run_capture(self._payload(), store, ip, n_threshold=5, spawner=calls.append)
            self.assertEqual(calls, [])

    def test_child_session_is_a_noop(self):
        os.environ["TALON_DISTILL_CHILD"] = "1"
        try:
            with tempfile.TemporaryDirectory() as d:
                store, ip = os.path.join(d, "store"), installed_with(d, {"talon-plugin-manager": ""})
                calls = []
                wrote = run_capture(self._payload(), store, ip, n_threshold=1, spawner=calls.append)
                self.assertEqual(wrote, [])
                self.assertEqual(calls, [])
        finally:
            del os.environ["TALON_DISTILL_CHILD"]

    def test_auto_pass_is_dry_run_by_default(self):
        os.environ.pop("TALON_DISTILL_AUTOPOST", None)
        os.environ.pop("TALON_DISTILL_DRY_RUN", None)
        env = _spawn_env("myplugin")
        self.assertEqual(env["TALON_DISTILL_CHILD"], "1")
        self.assertEqual(env["TALON_DISTILL_DRY_RUN"], "1")          # safe default: don't auto-post
        self.assertTrue(env["TALON_DISTILL_DRY_LOG"].endswith("pending/myplugin.log"))

    def test_autopost_opt_in_disables_dry_run(self):
        os.environ["TALON_DISTILL_AUTOPOST"] = "1"
        os.environ["TALON_DISTILL_DRY_RUN"] = "1"  # even if inherited, autopost must clear it
        try:
            env = _spawn_env("myplugin")
            self.assertEqual(env["TALON_DISTILL_CHILD"], "1")
            self.assertNotIn("TALON_DISTILL_DRY_RUN", env)
        finally:
            del os.environ["TALON_DISTILL_AUTOPOST"]
            os.environ.pop("TALON_DISTILL_DRY_RUN", None)

    def test_spawn_command_scopes_tools(self):
        cmd = _spawn_command("p")
        self.assertEqual(cmd[0], "claude")
        self.assertIn("-p", cmd)
        self.assertIn("--allowedTools", cmd)
        self.assertIn("Bash(python3:*)", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)   # never blanket-bypass
