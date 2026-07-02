"""PostToolUse re-assert fires only for Talon-registry skills, never for skill-feedback itself."""
import json
import unittest

import feedback_post_skill as h

REG = {"onboard-plugin": "/p/onboard", "talon-plugin-manager": "/p/tpm"}


class TestReassert(unittest.TestCase):
    def test_talon_skill_reasserts(self):
        note = h.reassert_for({"tool_name": "Skill",
                               "tool_input": {"skill": "onboard-plugin:onboard-plugin"}}, REG)
        self.assertIsNotNone(note)
        self.assertIn("skill-feedback", note)

    def test_skill_feedback_itself_is_silent(self):
        note = h.reassert_for({"tool_name": "Skill",
                               "tool_input": {"skill": "talon-plugin-manager:skill-feedback"}}, REG)
        self.assertIsNone(note)

    def test_non_talon_skill_is_silent(self):
        note = h.reassert_for({"tool_name": "Skill",
                               "tool_input": {"skill": "some-other:thing"}}, REG)
        self.assertIsNone(note)

    def test_non_skill_tool_is_silent(self):
        self.assertIsNone(h.reassert_for({"tool_name": "Bash", "tool_input": {"command": "ls"}}, REG))


if __name__ == "__main__":
    unittest.main()
