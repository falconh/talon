import unittest
from transcript import ParsedTranscript, ToolCall
from windows import per_plugin_friction

DOMAIN = {"terraform-module-steering": {"globs": ["**/*.tf"], "cmds": ["terraform", "tofu"]}}


class TestWindows(unittest.TestCase):
    def test_clean_usage_does_not_inherit_other_plugin_friction(self):
        calls = [
            ToolCall("s", "Skill", {"skill": "talon-plugin-manager:onboard-plugin"}, seq=0),
            ToolCall("w", "Write", {"file_path": "infra/main.tf"}, seq=1),
            ToolCall("b1", "Bash", {"command": "terraform apply"}, is_error=True, result_text="Error: boom", seq=2),
            ToolCall("b2", "Bash", {"command": "terraform apply"}, is_error=True, result_text="Error: boom", seq=4),
        ]
        parsed = ParsedTranscript(tool_calls=calls,
                                  user_texts=["no, that's wrong"],
                                  user_events=[(3, "no, that's wrong")])
        fm = per_plugin_friction(parsed, {"talon-plugin-manager"},
                                 {"terraform-module-steering"}, DOMAIN)
        # usage window = [0,1): only the Skill call -> clean
        self.assertFalse(fm["talon-plugin-manager"]["has_tool_errors"])
        self.assertEqual(fm["talon-plugin-manager"]["error_count"], 0)
        self.assertFalse(fm["talon-plugin-manager"]["correction"])
        # under-trigger window = [1,4]: 2 errors + correction text at seq 3
        self.assertTrue(fm["terraform-module-steering"]["has_tool_errors"])
        self.assertEqual(fm["terraform-module-steering"]["error_count"], 2)
        self.assertTrue(fm["terraform-module-steering"]["correction"])


if __name__ == "__main__":
    unittest.main()
