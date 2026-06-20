"""Tests for capture-hook.sh — the SessionEnd guard that keeps a missing python3 from
failing the distill capture silently."""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "capture-hook.sh")
SH = shutil.which("sh") or "/bin/sh"


class TestCaptureHook(unittest.TestCase):
    def _run(self, path, home):
        return subprocess.run(
            [SH, HOOK], input=b"{}", env={"PATH": path, "HOME": home},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def test_missing_python3_writes_breadcrumb_and_exits_zero(self):
        # Build a PATH that has the coreutils the guard needs but NO python3.
        needed = {u: shutil.which(u) for u in ("dirname", "mkdir", "date")}
        missing = [u for u, p in needed.items() if not p]
        if missing:
            self.skipTest(f"coreutils not found: {missing}")
        with tempfile.TemporaryDirectory() as td:
            bindir, home = os.path.join(td, "bin"), os.path.join(td, "home")
            os.makedirs(bindir)
            os.makedirs(home)
            for util, src in needed.items():
                os.symlink(src, os.path.join(bindir, util))
            self.assertIsNone(shutil.which("python3", path=bindir))  # python3 truly absent

            result = self._run(bindir, home)

            self.assertEqual(result.returncode, 0)  # never blocks session end
            log = os.path.join(home, ".claude", "talon-distill", "runtime.log")
            self.assertTrue(os.path.exists(log), "breadcrumb not written")
            with open(log) as fh:
                self.assertIn("python3 not found", fh.read())

    def test_python3_present_execs_capture_and_leaves_no_breadcrumb(self):
        if not shutil.which("python3"):
            self.skipTest("python3 not on PATH")
        with tempfile.TemporaryDirectory() as home:
            # Real PATH (has python3) but an empty HOME: capture.py finds no registry and
            # exits 0 without writing a breadcrumb.
            result = self._run(os.environ.get("PATH", ""), home)
            self.assertEqual(result.returncode, 0)
            log = os.path.join(home, ".claude", "talon-distill", "runtime.log")
            self.assertFalse(os.path.exists(log), "breadcrumb written despite python3 present")


if __name__ == "__main__":
    unittest.main()
