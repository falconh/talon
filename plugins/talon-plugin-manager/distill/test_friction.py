import unittest
from transcript import ToolCall
from friction import scan_friction


def err(name, sig):
    return ToolCall(id="x", name=name, input={"command": name}, is_error=True, result_text=sig)


class TestFriction(unittest.TestCase):
    def test_no_friction_clean_session(self):
        h = scan_friction([ToolCall("a", "Bash", {"command": "ls"}, False, "ok")], ["thanks"])
        self.assertFalse(h.has_tool_errors)
        self.assertEqual(h.repeated_error_count, 0)
        self.assertFalse(h.correction)

    def test_detects_errors_and_repeats(self):
        calls = [err("Bash", "Error: boom"), err("Bash", "Error: boom")]
        h = scan_friction(calls, [])
        self.assertTrue(h.has_tool_errors)
        self.assertEqual(h.error_count, 2)
        self.assertEqual(h.repeated_error_count, 2)

    def test_detects_correction_language(self):
        h = scan_friction([], ["No, that's wrong"])
        self.assertTrue(h.correction)

    def test_detects_retry_repeated_command(self):
        c = [ToolCall("1", "Bash", {"command": "terraform apply"}, False, "x"),
             ToolCall("2", "Bash", {"command": "terraform apply"}, False, "x")]
        self.assertTrue(scan_friction(c, []).retry)

    def test_detects_abandonment(self):
        self.assertTrue(scan_friction([], ["ok never mind, forget it"]).abandonment)

    def test_as_dict_roundtrips_keys(self):
        d = scan_friction([], []).as_dict()
        self.assertEqual(set(d), {"has_tool_errors", "error_count", "repeated_error_count", "retry", "correction", "abandonment"})
