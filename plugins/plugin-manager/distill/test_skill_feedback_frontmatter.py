"""skill-feedback SKILL.md must have YAML frontmatter with both name and description (Codex needs
name; Claude Code triggers on description), and point at feedback_emit.py."""
import os
import unittest

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "skills", "skill-feedback", "SKILL.md")


class TestSkillFeedbackFrontmatter(unittest.TestCase):
    def setUp(self):
        with open(SKILL, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_has_frontmatter_name_and_description(self):
        self.assertTrue(self.text.startswith("---\n"))
        fm = self.text.split("---\n", 2)[1]
        self.assertIn("name: skill-feedback", fm)
        self.assertIn("description:", fm)

    def test_references_feedback_emit(self):
        self.assertIn("feedback_emit.py", self.text)

    def test_states_abstraction_first(self):
        self.assertIn("abstraction-first", self.text.lower().replace("abstraction first", "abstraction-first"))


if __name__ == "__main__":
    unittest.main()
