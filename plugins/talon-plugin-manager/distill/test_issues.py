import unittest
from issues import find_existing, open_issue


class FakeRunner:
    def __init__(self, code=0, out="", err=""):
        self.code, self.out, self.err, self.calls = code, out, err, []

    def __call__(self, args):
        self.calls.append(args)
        return self.code, self.out, self.err


class TestIssues(unittest.TestCase):
    def test_find_existing_matches_fingerprint_in_body(self):
        r = FakeRunner(out='[{"number":7,"state":"OPEN","body":"x <!-- distill-fp: abc123abc123 -->","title":"t"}]')
        found = find_existing("o/r", "abc123abc123", r)
        self.assertEqual(found["number"], 7)

    def test_find_existing_returns_none_when_no_body_match(self):
        r = FakeRunner(out='[{"number":1,"state":"OPEN","body":"unrelated","title":"t"}]')
        self.assertIsNone(find_existing("o/r", "abc123abc123", r))

    def test_open_issue_passes_labels(self):
        r = FakeRunner(out="https://github.com/o/r/issues/9\n")
        url = open_issue("o/r", "Title", "Body", ["distillation"], r)
        self.assertEqual(url, "https://github.com/o/r/issues/9")
        self.assertIn("--label", r.calls[0])
        self.assertIn("distillation", r.calls[0])

    def test_dry_run_never_shells_out_and_logs(self):
        import os
        import tempfile
        from issues import default_runner
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "gh.log")
            os.environ["TALON_DISTILL_DRY_RUN"] = "1"
            os.environ["TALON_DISTILL_DRY_LOG"] = log
            try:
                code, out, _ = default_runner(["gh", "issue", "create", "--title", "x"])
                self.assertEqual(code, 0)
                self.assertIn("github.com", out)               # canned url, no network
                _, list_out, _ = default_runner(["gh", "issue", "list", "--repo", "o/r"])
                self.assertEqual(list_out.strip(), "[]")        # no existing => no dedup surprises
                with open(log) as fh:
                    logged = fh.read()
                self.assertIn("issue create", logged)           # the gh call was recorded, not run
            finally:
                del os.environ["TALON_DISTILL_DRY_RUN"]
                del os.environ["TALON_DISTILL_DRY_LOG"]
