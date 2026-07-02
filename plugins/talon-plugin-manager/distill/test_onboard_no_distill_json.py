# plugins/talon-plugin-manager/distill/test_onboard_no_distill_json.py
"""onboard-plugin must no longer mention distill.json / under-trigger / domain-signals now that
under-trigger detection is retired."""
import json
import os
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SKILL = os.path.join(BASE, "skills", "onboard-plugin", "SKILL.md")
EVALS = os.path.join(BASE, "skills", "onboard-plugin", "evals", "evals.json")
REF = os.path.join(BASE, "references", "domain-signals.md")


class TestOnboardCleaned(unittest.TestCase):
    def test_skill_has_no_distill_json_mentions(self):
        t = open(SKILL, encoding="utf-8").read().lower()
        for term in ("distill.json", "domain-signals", "under-trigger", "under_trigger"):
            self.assertNotIn(term, t, f"onboard SKILL.md still mentions {term}")

    def test_evals_dropped_distill_backfill(self):
        data = json.load(open(EVALS, encoding="utf-8"))
        self.assertTrue(all("distill.json" not in json.dumps(e) for e in data["evals"]))
        self.assertEqual(len(data["evals"]), 3)

    def test_domain_signals_reference_deleted(self):
        self.assertFalse(os.path.exists(REF))


if __name__ == "__main__":
    unittest.main()
