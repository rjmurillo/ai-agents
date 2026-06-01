"""Tests for scripts/redact_secrets.py (issue #1975, CWE-209/CWE-532)."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from redact_secrets import main, redact  # noqa: E402


class TestTokenShapesRedacted:
    def test_bearer_token(self):
        r = redact("auth header: Bearer abc123DEF456ghijkl+/=")
        assert "[redacted: bearer-token]" in r.text
        assert "abc123DEF456ghijkl" not in r.text
        assert "bearer-token" in r.reasons

    def test_github_token(self):
        r = redact("token ghp_" + "A" * 36 + " end")
        assert "[redacted: github-token]" in r.text
        assert "ghp_" + "A" * 36 not in r.text

    def test_stripe_key(self):
        r = redact("key sk_live_abcdef0123456789 done")
        assert "[redacted: stripe-key]" in r.text

    def test_aws_access_key_id(self):
        r = redact("AKIAIOSFODNN7EXAMPLE is the id")
        assert "[redacted: aws-access-key-id]" in r.text
        assert "AKIAIOSFODNN7EXAMPLE" not in r.text

    def test_jwt(self):
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        r = redact(f"jwt={jwt}")
        assert "[redacted: jwt]" in r.text
        assert jwt not in r.text

    def test_email(self):
        r = redact("blocked: alice@corp.example.com on prod")
        assert "[redacted: email]" in r.text
        assert "alice@corp.example.com" not in r.text

    def test_email_single_label_domain(self):
        # Single-label corporate forms (Alice@corp) carry PII too.
        r = redact("contact Alice@corp now")
        assert "[redacted: email]" in r.text
        assert "Alice@corp" not in r.text
        assert "now" in r.text

    def test_email_unicode_local_part(self):
        r = redact("ping café@example.com please")
        assert "[redacted: email]" in r.text
        assert "café@example.com" not in r.text

    def test_private_key_block(self):
        key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
        r = redact(f"here:\n{key}\nafter")
        assert "[redacted: private-key]" in r.text
        assert "MIIEowIBAAKCAQEA" not in r.text
        assert "after" in r.text

    def test_truncated_private_key_block(self):
        # A pasted BEGIN line plus key material with no END marker must still
        # be redacted (cursor: truncated PEM blocks not redacted).
        truncated = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAtruncated"
        r = redact(f"leaked:\n{truncated}")
        assert "[redacted: private-key]" in r.text
        assert "MIIEowIBAAKCAQEAtruncated" not in r.text

    def test_long_hex_secret(self):
        r = redact("hash " + "a" * 40 + " value")
        assert "[redacted: hex-secret]" in r.text

    def test_long_hex_secret_after_word_char(self):
        # A 32+ hex run immediately after `_` has no \b boundary; the rule must
        # still redact it (cursor: long hex after word chars).
        r = redact("token_" + "a" * 40 + " value")
        assert "[redacted: hex-secret]" in r.text
        assert "a" * 40 not in r.text


class TestRealisticHaltBlockEvidence:
    def test_issue_example(self):
        # The exact shape from the issue: "Alice@corp on prod-east-12.internal
        # blocked on Bearer abc..."
        evidence = "Alice@corp.example.com on prod-east-12.internal blocked on Bearer abc123def456ghi789"
        r = redact(evidence)
        assert "Alice@corp.example.com" not in r.text
        assert "abc123def456ghi789" not in r.text
        assert "email" in r.reasons
        assert "bearer-token" in r.reasons


class TestNoFalsePositives:
    def test_plain_prose_untouched(self):
        text = "The system shall send a reset email within 5 seconds so that the user is not blocked."
        r = redact(text)
        assert r.text == text
        assert not r.redacted

    def test_short_hex_untouched(self):
        # A short hex run (e.g. a 7-char abbreviated SHA) is below the threshold.
        r = redact("commit ec49950 fixed it")
        assert r.text == "commit ec49950 fixed it"


class TestHexCaveat:
    def test_include_hex_false_preserves_sha(self):
        sha = "e" * 40
        r = redact(f"endingCommit: {sha}", include_hex=False)
        assert sha in r.text
        assert not r.redacted

    def test_include_hex_false_still_redacts_tokens(self):
        r = redact("Bearer abc123def456ghi", include_hex=False)
        assert "[redacted: bearer-token]" in r.text


class TestCli:
    def test_stdin_redaction(self, capsys):
        with patch.object(sys, "stdin", io.StringIO("Bearer abc123def456ghi789")):
            rc = main([])
        assert rc == 0
        assert "[redacted: bearer-token]" in capsys.readouterr().out

    def test_file_redaction(self, tmp_path, capsys):
        p = tmp_path / "in.txt"
        p.write_text("email alice@corp.example.com here", encoding="utf-8")
        rc = main([str(p)])
        assert rc == 0
        assert "[redacted: email]" in capsys.readouterr().out

    def test_too_many_args_is_usage_error(self):
        assert main(["a", "b"]) == 2

    def test_invalid_utf8_file_is_usage_error(self, tmp_path):
        # Invalid UTF-8 must surface as ADR-035 exit code 2, not a traceback
        # (cursor: invalid UTF-8 crashes CLI).
        p = tmp_path / "bad.bin"
        p.write_bytes(b"\xff\xfe leaked Bearer abc123def456ghi789")
        assert main([str(p)]) == 2
