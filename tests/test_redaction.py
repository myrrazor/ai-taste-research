import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.redaction import redact_payload, redact_secrets


class RedactionTests(unittest.TestCase):
    def test_redacts_common_credential_shapes(self):
        # Fixtures are assembled at runtime so the repository's own privacy scan does not
        # see token-shaped literals in this source file.
        letters = "abcdefghijklmnopqrstuvwxyz"
        pem = "PRIVATE KEY-----"
        jwt = ".".join(
            (
                "eyJ" + "hbGciOiJIUzI1NiJ9",
                "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0",
                "dGVz" + "dHNpZ25hdHVyZTEyMw",
            )
        )
        # (surrounding text template, secret, expected marker)
        cases = {
            "openai": ("key {} ok", f"sk-{letters}0123456789", "api-key"),
            "openai-legacy-length": ("{}", "sk-abcdefghijklmnop", "api-key"),
            "openai-project": ("{}", f"sk-proj-{letters}0123456789ABCDEFGH", "api-key"),
            "anthropic": ("{}", f"sk-ant-api03-{letters}0123456789", "api-key"),
            "github-classic": (
                "token {} here",
                "ghp" + "_" + letters.upper() + letters[:10] + "0123",
                "github-token",
            ),
            "github-fine-grained": (
                "{}",
                "github" + "_pat_" + "11ABCDEFG0123456789_" + letters,
                "github-token",
            ),
            "aws": ("id {}", "AKIA" + "IOSFODNN7EXAMPLE", "aws-access-key"),
            "slack": ("{}", "xoxb-1234567890-abcdefghijk", "slack-token"),
            "google": ("{}", f"AIzaSyA-{letters}01234", "google-api-key"),
            "jwt": (
                "{}",
                jwt,
                "jwt",
            ),
            "bearer": (
                "Authorization: {}",
                f"Bearer 0123456789{letters}",
                "bearer-token",
            ),
            "private-key": (
                "{}",
                f"-----BEGIN RSA {pem}\nMIIEow\n-----END RSA {pem}",
                "private-key",
            ),
        }
        for label, (template, secret, kind) in cases.items():
            with self.subTest(label=label):
                redacted = redact_secrets(template.format(secret))
                self.assertIn(f"[REDACTED-{kind}]", redacted)
                self.assertNotIn(secret, redacted)
                self.assertEqual(redacted, template.format(f"[REDACTED-{kind}]"))

    def test_redacts_assigned_secret_values_but_keeps_key_names(self):
        self.assertEqual(
            redact_secrets("api_key=supersecretvalue123 done"),
            "api_key=[REDACTED-assigned-secret] done",
        )
        self.assertEqual(
            redact_secrets('password: "correct-horse-battery"'),
            'password: "[REDACTED-assigned-secret]"',
        )
        self.assertEqual(
            redact_secrets("ACCESS_TOKEN = 'abcdefghijklmnop'"),
            "ACCESS_TOKEN = '[REDACTED-assigned-secret]'",
        )

    def test_leaves_ordinary_research_text_alone(self):
        samples = (
            "The risk-adjusted-return-calculation took 3 seconds.",
            "A desk-based workflow with task-management-system-for-teams tooling.",
            "token: the smallest unit the parser emits",
            "The password policy requires 12 characters and a rotation every 90 days.",
            "The bearer of bad news still deserves a clear message.",
            "Secret sauce is specificity; secret: yes.",
            "Ask before acting; sk-8 is a valid chess square label.",
            "Rotate the API key monthly and never paste it into TASTE.md.",
        )
        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(redact_secrets(text), text)

    def test_payload_redaction_is_recursive_and_keeps_structure(self):
        payload = {
            "prompt": "sk-abcdefghijklmnopqrstuvwxyz0123456789",
            "selected_candidate": {"text": "plain", "score": 2, "reasons": ["+1 x"]},
            "rejected_candidates": [{"text": "Bearer 0123456789abcdefghijklmnopqrstuvwxyz"}],
            "count": 3,
            "flag": None,
        }

        redacted = redact_payload(payload)

        self.assertEqual(redacted["prompt"], "[REDACTED-api-key]")
        self.assertEqual(redacted["selected_candidate"], payload["selected_candidate"])
        self.assertEqual(
            redacted["rejected_candidates"][0]["text"], "[REDACTED-bearer-token]"
        )
        self.assertEqual(redacted["count"], 3)
        self.assertIsNone(redacted["flag"])
        self.assertEqual(payload["prompt"], "sk-abcdefghijklmnopqrstuvwxyz0123456789")


if __name__ == "__main__":
    unittest.main()
