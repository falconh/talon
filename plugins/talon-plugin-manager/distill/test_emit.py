import json
import tempfile
import unittest
from emit import emit_finding


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        return self.responses.pop(0)


class FakeRunner:
    def __init__(self, list_out="[]"):
        self.list_out, self.calls = list_out, []

    def __call__(self, args):
        self.calls.append(args)
        if args[:3] == ["gh", "issue", "list"]:
            return 0, self.list_out, ""
        if args[:3] == ["gh", "issue", "create"]:
            return 0, "https://github.com/o/r/issues/1\n", ""
        return 0, "", ""


BASE = {"repo": "o/r", "plugin": "p", "decision": "improve_skill",
        "anchor": "missing remote guidance", "title": "Improve p", "body": "Clean body."}


class TestEmit(unittest.TestCase):
    def test_opens_when_no_existing(self):
        r = FakeRunner(list_out="[]")
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(BASE, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "opened")
        self.assertTrue(any(a[:3] == ["gh", "issue", "create"] for a in r.calls))

    def test_updates_when_open_exists(self):
        from fingerprint import finding_fingerprint
        fp = finding_fingerprint("p", "improve_skill", "missing remote guidance")
        r = FakeRunner(list_out=json.dumps([{"number": 5, "state": "OPEN", "body": f"<!-- distill-fp: {fp} -->", "title": "t"}]))
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(BASE, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "updated")
        self.assertTrue(any(a[:3] == ["gh", "issue", "comment"] for a in r.calls))

    def test_reopens_when_closed_exists(self):
        from fingerprint import finding_fingerprint
        fp = finding_fingerprint("p", "improve_skill", "missing remote guidance")
        r = FakeRunner(list_out=json.dumps([{"number": 6, "state": "CLOSED", "body": f"<!-- distill-fp: {fp} -->", "title": "t"}]))
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(BASE, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "reopened")
        self.assertTrue(any(a[:3] == ["gh", "issue", "reopen"] for a in r.calls))

    def test_quarantines_when_secret_present(self):
        r = FakeRunner(list_out="[]")
        dirty = {**BASE, "body": "leak AKIA1234567890ABCD12 oops"}
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(dirty, runner=r, quarantine_dir=q)
        self.assertEqual(res["status"], "quarantined")
        self.assertFalse(any(a[:3] == ["gh", "issue", "create"] for a in r.calls))  # never posted

    def test_quarantines_on_denylisted_term(self):
        r = FakeRunner(list_out="[]")
        dirty = {**BASE, "body": "the AcmeCorp prod cluster broke the skill"}
        with tempfile.TemporaryDirectory() as q:
            res = emit_finding(dirty, runner=r, quarantine_dir=q, denylist=["AcmeCorp"])
        self.assertEqual(res["status"], "quarantined")
        self.assertFalse(any(a[:3] == ["gh", "issue", "create"] for a in r.calls))

    def test_defers_when_no_transport(self):
        import os
        with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as pend:
            res = emit_finding(BASE, quarantine_dir=q, pending_dir=pend, backend="none")
            self.assertEqual(res["status"], "deferred")
            self.assertTrue(res["path"].startswith(pend))
            self.assertTrue(os.path.exists(res["path"]))

    def test_dry_run_opens_by_default_and_dedups_with_existing_env(self):
        import os
        saved = {k: os.environ.get(k) for k in
                 ("TALON_DISTILL_DRY_RUN", "TALON_DISTILL_DRY_EXISTING",
                  "TALON_DISTILL_DRY_EXISTING_STATE", "TALON_DISTILL_DRY_LOG")}
        try:
            with tempfile.TemporaryDirectory() as q, tempfile.TemporaryDirectory() as log:
                os.environ["TALON_DISTILL_DRY_RUN"] = "1"
                os.environ["TALON_DISTILL_DRY_LOG"] = os.path.join(log, "dry.log")
                os.environ.pop("TALON_DISTILL_DRY_EXISTING", None)
                # default dry run: no prior issue -> opened
                self.assertEqual(emit_finding(BASE, quarantine_dir=q)["status"], "opened")
                # simulate a prior OPEN issue with the same fingerprint -> updated
                os.environ["TALON_DISTILL_DRY_EXISTING"] = "1"
                self.assertEqual(emit_finding(BASE, quarantine_dir=q)["status"], "updated")
                # simulate a prior CLOSED issue -> reopened
                os.environ["TALON_DISTILL_DRY_EXISTING_STATE"] = "CLOSED"
                self.assertEqual(emit_finding(BASE, quarantine_dir=q)["status"], "reopened")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_api_backend_opens_via_http(self):
        import issues
        http = FakeHttp([(200, {"items": []}), (201, {"html_url": "https://github.com/o/r/issues/9"})])
        orig = issues.api_request
        issues.api_request = http  # call-time global lookup picks this up
        try:
            with tempfile.TemporaryDirectory() as q:
                res = emit_finding(BASE, quarantine_dir=q, backend="api")
        finally:
            issues.api_request = orig
        self.assertEqual(res["status"], "opened")
        self.assertEqual(res["url"], "https://github.com/o/r/issues/9")
