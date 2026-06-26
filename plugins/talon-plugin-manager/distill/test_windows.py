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


    def test_usage_window_closed_by_next_skill_call(self):
        calls = [
            ToolCall("sa", "Skill", {"skill": "plugin-a:x"}, seq=0),
            ToolCall("e1", "Bash", {"command": "boom"}, is_error=True, result_text="Error: A", seq=1),
            ToolCall("sb", "Skill", {"skill": "plugin-b:y"}, seq=2),
            ToolCall("e2", "Bash", {"command": "boom"}, is_error=True, result_text="Error: B", seq=3),
        ]
        parsed = ParsedTranscript(tool_calls=calls, user_texts=[], user_events=[])
        fm = per_plugin_friction(parsed, {"plugin-a", "plugin-b"}, set(), {})
        # plugin-a window = [0,2): only e1; plugin-b window = [2, end): only e2
        self.assertEqual(fm["plugin-a"]["error_count"], 1)
        self.assertEqual(fm["plugin-b"]["error_count"], 1)

    def test_usage_only_window_open_to_session_end(self):
        calls = [
            ToolCall("s", "Skill", {"skill": "plugin-a:x"}, seq=0),
            ToolCall("e", "Bash", {"command": "boom"}, is_error=True, result_text="Error", seq=1),
        ]
        parsed = ParsedTranscript(tool_calls=calls, user_texts=["give up"], user_events=[(2, "give up")])
        fm = per_plugin_friction(parsed, {"plugin-a"}, set(), {})
        self.assertTrue(fm["plugin-a"]["has_tool_errors"])   # open window includes the later error
        self.assertEqual(fm["plugin-a"]["error_count"], 1)
        self.assertTrue(fm["plugin-a"]["abandonment"])        # and the trailing user text


if __name__ == "__main__":
    unittest.main()
