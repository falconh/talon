import os
import unittest
from issues import find_existing, open_issue, comment, reopen, select_backend


class FakeHttp:
    """Stand-in for issues.api_request: returns queued (status, json) per call."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        return self.responses.pop(0)


class TestBackendSelect(unittest.TestCase):
    def setUp(self):
        os.environ.pop("TALON_DISTILL_DRY_RUN", None)

    def test_prefers_gh_then_api_then_none(self):
        self.assertEqual(select_backend(have_gh=True, token=""), "gh")
        self.assertEqual(select_backend(have_gh=False, token="tok"), "api")
        self.assertEqual(select_backend(have_gh=False, token=""), "none")

    def test_dry_run_overrides(self):
        os.environ["TALON_DISTILL_DRY_RUN"] = "1"
        try:
            self.assertEqual(select_backend(have_gh=True, token="tok"), "dry")
        finally:
            del os.environ["TALON_DISTILL_DRY_RUN"]


class TestApiTransport(unittest.TestCase):
    def test_find_existing_via_search_normalizes_state(self):
        http = FakeHttp([(200, {"items": [
            {"number": 12, "state": "closed", "body": "x <!-- distill-fp: abc123abc123 -->", "title": "t"}]})])
        found = find_existing("o/r", "abc123abc123", backend="api", http=http)
        self.assertEqual(found["number"], 12)
        self.assertEqual(found["state"], "CLOSED")
        self.assertEqual(http.calls[0][0], "GET")
        self.assertIn("/search/issues", http.calls[0][1])

    def test_find_existing_no_match(self):
        http = FakeHttp([(200, {"items": [{"number": 1, "state": "open", "body": "unrelated", "title": "t"}]})])
        self.assertIsNone(find_existing("o/r", "abc123abc123", backend="api", http=http))

    def test_open_issue_posts_and_returns_url(self):
        http = FakeHttp([(201, {"html_url": "https://github.com/o/r/issues/9"})])
        url = open_issue("o/r", "T", "B", ["distillation"], backend="api", http=http)
        self.assertEqual(url, "https://github.com/o/r/issues/9")
        self.assertEqual(http.calls[0][0], "POST")
        self.assertEqual(http.calls[0][2]["labels"], ["distillation"])

    def test_comment_and_reopen(self):
        h1 = FakeHttp([(201, {})])
        comment("o/r", 5, "note", backend="api", http=h1)
        self.assertIn("/issues/5/comments", h1.calls[0][1])
        h2 = FakeHttp([(200, {})])
        reopen("o/r", 5, backend="api", http=h2)
        self.assertEqual(h2.calls[0][0], "PATCH")
        self.assertEqual(h2.calls[0][2]["state"], "open")


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
