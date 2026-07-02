"""Tests for feedback_emit.file_feedback — the dedup-free scrub→file path."""
import os
import tempfile
import unittest

import feedback_emit
import issues

CLEAN = {"repo": "falconh/talon", "plugin": "onboard-plugin", "skill": "talon-plugin-manager:onboard-plugin",
         "title": "[feedback] onboard-plugin validator path guidance unclear",
         "body": "The skill's verification step points at a path that does not resolve for a local plugin."}
DIRTY = {**CLEAN, "title": "[feedback] leak", "body": "the key AKIA1234567890ABCD00 was printed by the step"}


class TestFileFeedback(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.q = os.path.join(self.td.name, "_quarantine")
        self.pending = os.path.join(self.td.name, "pending")
        self.dry_log = os.path.join(self.td.name, "dry_run.log")
        os.environ["TALON_DISTILL_DRY_RUN"] = "1"
        os.environ["TALON_DISTILL_DRY_LOG"] = self.dry_log

    def tearDown(self):
        self.td.cleanup()
        os.environ.pop("TALON_DISTILL_DRY_RUN", None)
        os.environ.pop("TALON_DISTILL_DRY_LOG", None)

    def test_clean_finding_opens_and_logs_gh_create(self):
        res = feedback_emit.file_feedback(CLEAN, quarantine_dir=self.q, pending_dir=self.pending, denylist=[])
        self.assertEqual(res["status"], "opened")
        with open(self.dry_log, encoding="utf-8") as fh:
            log = fh.read()
        self.assertIn("gh issue create --repo falconh/talon", log)

    def test_secret_in_body_quarantines_and_does_not_file(self):
        res = feedback_emit.file_feedback(DIRTY, quarantine_dir=self.q, pending_dir=self.pending, denylist=[])
        self.assertEqual(res["status"], "quarantined")
        self.assertTrue(os.path.isdir(self.q) and os.listdir(self.q))
        self.assertFalse(os.path.exists(self.dry_log), "must not reach gh create when quarantined")

    def test_no_backend_defers_to_pending(self):
        res = feedback_emit.file_feedback(CLEAN, quarantine_dir=self.q, pending_dir=self.pending,
                                          denylist=[], backend="none")
        self.assertEqual(res["status"], "deferred")
        self.assertTrue(os.listdir(self.pending))

    def test_denylist_term_quarantines(self):
        res = feedback_emit.file_feedback(CLEAN, quarantine_dir=self.q, pending_dir=self.pending,
                                          denylist=["acme.corp"], backend="dry")
        # CLEAN has no denylist term, so it opens; now plant one:
        dirty = {**CLEAN, "body": "the step referenced db.acme.corp directly"}
        res = feedback_emit.file_feedback(dirty, quarantine_dir=self.q, pending_dir=self.pending,
                                          denylist=["acme.corp"], backend="dry")
        self.assertEqual(res["status"], "quarantined")

    def test_repeated_defer_does_not_overwrite(self):
        a = {**CLEAN, "body": "first body"}
        b = {**CLEAN, "body": "second body"}  # same repo/plugin/skill/title, different body
        r1 = feedback_emit.file_feedback(a, quarantine_dir=self.q, pending_dir=self.pending,
                                         denylist=[], backend="none")
        r2 = feedback_emit.file_feedback(b, quarantine_dir=self.q, pending_dir=self.pending,
                                         denylist=[], backend="none")
        self.assertEqual(r1["status"], "deferred")
        self.assertEqual(r2["status"], "deferred")
        self.assertNotEqual(r1["path"], r2["path"], "two deferrals must not collide")
        self.assertEqual(len(os.listdir(self.pending)), 2)


if __name__ == "__main__":
    unittest.main()
