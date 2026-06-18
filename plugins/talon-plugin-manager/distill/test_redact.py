import unittest
from redact import scan_secrets, is_clean


class TestRedact(unittest.TestCase):
    def test_clean_text_passes(self):
        self.assertTrue(is_clean("The onboard-plugin skill lacked guidance on remote sources."))

    def test_aws_access_key(self):
        kinds = {k for k, _ in scan_secrets("key AKIA1234567890ABCD12 here")}
        self.assertIn("aws_access_key", kinds)

    def test_private_key_block(self):
        self.assertFalse(is_clean("-----BEGIN RSA PRIVATE KEY-----\nabc"))

    def test_github_and_slack_and_jwt(self):
        gh = "ghp_" + "a" * 36
        slack = "xoxb-123456789012-abcdEFGhijkl"
        jwt = "eyJabcdefghij.eyJklmnopqrst.signature123"
        kinds = {k for k, _ in scan_secrets(f"{gh} {slack} {jwt}")}
        self.assertSetEqual(kinds & {"github_token", "slack_token", "jwt"}, {"github_token", "slack_token", "jwt"})

    def test_account_id_arn_ip_email(self):
        text = "acct 123456789012 arn:aws:iam::123456789012:role/x ip 10.0.3.4 mail a@b.com"
        kinds = {k for k, _ in scan_secrets(text)}
        for k in ("aws_account_id", "arn", "private_ip", "email"):
            self.assertIn(k, kinds)

    def test_public_ip_not_flagged_as_private(self):
        kinds = {k for k, _ in scan_secrets("8.8.8.8")}
        self.assertNotIn("private_ip", kinds)

    def test_denylist_flags_org_terms_case_insensitively(self):
        text = "The skill failed on the AcmeCorp internal cluster."
        self.assertTrue(is_clean(text))  # no denylist => clean
        hits = scan_secrets(text, denylist=["acmecorp", "internal.example.com"])
        kinds = {k for k, _ in hits}
        self.assertIn("denylisted", kinds)
        self.assertFalse(is_clean(text, denylist=["acmecorp"]))

    def test_denylist_none_or_empty_is_noop(self):
        self.assertTrue(is_clean("plain text", denylist=None))
        self.assertTrue(is_clean("plain text", denylist=[]))
