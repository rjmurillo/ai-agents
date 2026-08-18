"""Tests for scripts/redact_secrets.py (issue #1975, CWE-209/CWE-532)."""
# taste-lint: ignore file-size, one adversarial redaction matrix shares serialization fixtures.

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from redact_secrets import main, redact, redact_ci_sink  # noqa: E402


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
        jwt = ".".join(
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
                "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            )
        )
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
        evidence = (
            "Alice@corp.example.com on prod-east-12.internal blocked on Bearer abc123def456ghi789"
        )
        r = redact(evidence)
        assert "Alice@corp.example.com" not in r.text
        assert "abc123def456ghi789" not in r.text
        assert "email" in r.reasons
        assert "bearer-token" in r.reasons


class TestNoFalsePositives:
    def test_plain_prose_untouched(self):
        text = (
            "The system shall send a reset email within 5 seconds so that the user is not blocked."
        )
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


class TestCiSinkWrappers:
    def test_url_userinfo_redaction_is_scheme_and_case_independent(self):
        for scheme in ("http", "HTTPS", "ftp+ssh"):
            value = f"{scheme}://user:password@example.com/path"

            result = redact_ci_sink(value)

            assert "user:password@" not in result.text
            assert f"{scheme}://******@example.com/path" == result.text
            assert "url-credential" in result.reasons

    def test_url_token_only_userinfo_is_redacted(self):
        credential = "opaque-token~"
        value = f"https://{credential}@example.com/repo.git"

        result = redact_ci_sink(value)

        assert credential not in result.text
        assert result.text == "https://******@example.com/repo.git"
        assert result.reasons == ("url-credential",)

    @pytest.mark.parametrize("scheme", ["Basic", "Token", "Bearer"])
    @pytest.mark.parametrize(
        ("prefix", "suffix"),
        [
            ('{"Authorization":"', '","timeout":30}'),
            ('{\\"Authorization\\":\\"', '\\",\\"timeout\\":30}'),
        ],
    )
    def test_structured_authorization_redacts_only_the_credential_scalar(
        self,
        scheme,
        prefix,
        suffix,
    ):
        credential = "opaque-credential-value"
        value = f"{prefix}{scheme} {credential}{suffix}"

        result = redact_ci_sink(value, redact_assignments=False)

        assert credential not in result.text
        assert f"{prefix}{scheme} ***{suffix}" == result.text
        assert result.reasons == ("authorization-header",)

    def test_compact_authorization_preserves_trailing_fields(self):
        result = redact_ci_sink(
            "Authorization: Token opaque-value,timeout=30",
            redact_assignments=False,
        )

        assert result.text == "Authorization: Token ***,timeout=30"
        assert result.reasons == ("authorization-header",)

    @pytest.mark.parametrize("scheme", ["Basic", "Token", "Bearer"])
    def test_authorization_equals_redacts_the_complete_credential(self, scheme):
        credential = "ordinary-secret-value"
        value = f"Authorization={scheme} {credential},timeout=30"

        result = redact_ci_sink(value, redact_assignments=False)

        assert credential not in result.text
        assert result.text == f"Authorization={scheme} ***,timeout=30"
        assert result.reasons == ("authorization-header",)

    @pytest.mark.parametrize("serialization_depth", range(7))
    def test_serialized_authorization_escaped_slash_is_redacted(
        self,
        serialization_depth,
    ):
        value = '{"Authorization":"Token \\/opaqueCredentialValue123","timeout":30}'
        for _ in range(serialization_depth):
            value = json.dumps(value)[1:-1]

        result = redact_ci_sink(value, redact_assignments=False)

        assert "opaqueCredentialValue123" not in result.text
        assert "timeout" in result.text
        assert result.reasons == ("authorization-header",)

    @pytest.mark.parametrize("indicator", ["|", "|-", "|+", ">", ">-", ">+"])
    def test_yaml_block_credential_values_are_fully_redacted(self, indicator):
        value = f"password: {indicator}\n  first-secret-value\n  second-secret-value\ntimeout: 30"

        result = redact_ci_sink(value)

        assert result.text == "password: ***\ntimeout: 30"
        assert "first-secret-value" not in result.text
        assert "second-secret-value" not in result.text
        assert result.reasons == ("credential-assignment",)

    def test_nested_yaml_block_credential_preserves_sibling_field(self):
        value = (
            "config:\n  password: |\n    first-secret-value\n    second-secret-value\n  timeout: 30"
        )

        result = redact_ci_sink(value)

        assert result.text == "config:\n  password: ***\n  timeout: 30"
        assert "first-secret-value" not in result.text
        assert "second-secret-value" not in result.text

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (
                '{"token":["first-secret-value","second-secret-value"],"timeout":30}',
                '{"token":***,"timeout":30}',
            ),
            (
                '{"token":{"primary":"first-secret-value",'
                '"secondary":"second-secret-value"},"timeout":30}',
                '{"token":***,"timeout":30}',
            ),
            (
                '{\\"token\\":[\\"first-secret-value\\",'
                '\\"second-secret-value\\"],\\"timeout\\":30}',
                '{\\"token\\":***,\\"timeout\\":30}',
            ),
            (
                '{\\"token\\":{\\"primary\\":\\"first-secret-value\\",'
                '\\"secondary\\":\\"second-secret-value\\"},\\"timeout\\":30}',
                '{\\"token\\":***,\\"timeout\\":30}',
            ),
        ],
    )
    def test_nested_credential_values_are_fully_redacted(self, value, expected):
        result = redact_ci_sink(value)

        assert result.text == expected
        assert "first-secret-value" not in result.text
        assert "second-secret-value" not in result.text
        assert result.reasons == ("credential-assignment",)

    @pytest.mark.parametrize("serialization_depth", range(3))
    @pytest.mark.parametrize(
        ("raw_value", "raw_expected"),
        [
            (
                '{"token":["first-secret-value","second-secret-value"],"timeout":30}',
                '{"token":***,"timeout":30}',
            ),
            (
                '{"token":{"primary":"first-secret-value",'
                '"secondary":"second-secret-value"},"timeout":30}',
                '{"token":***,"timeout":30}',
            ),
        ],
    )
    def test_serialized_nested_credential_values_are_fully_redacted(
        self,
        serialization_depth,
        raw_value,
        raw_expected,
    ):
        value = raw_value
        expected = raw_expected
        for _ in range(serialization_depth):
            value = json.dumps(value)[1:-1]
            expected = json.dumps(expected)[1:-1]

        result = redact_ci_sink(value)

        assert result.text == expected
        assert "first-secret-value" not in result.text
        assert "second-secret-value" not in result.text

    @pytest.mark.parametrize("escaped", [False, True])
    def test_multiline_nested_credential_values_are_fully_redacted(self, escaped):
        value = '{"token":[\n"first-secret-value",\n"second-secret-value"\n],\n"timeout":30}'
        expected = '{"token":***,\n"timeout":30}'
        if escaped:
            value = json.dumps(value)[1:-1]
            expected = json.dumps(expected)[1:-1]

        result = redact_ci_sink(value)

        assert result.text == expected
        assert "first-secret-value" not in result.text
        assert "second-secret-value" not in result.text

    @pytest.mark.parametrize(
        "value",
        [
            '{"token":[\n"first-secret-value\nsecond-secret-value\n],"timeout":30}',
            '{"token":{"inner":"first-secret-value\nsecond-secret-value\n},"timeout":30}',
        ],
    )
    def test_malformed_multiline_credential_values_fail_closed(self, value):
        result = redact_ci_sink(value)

        assert "first-secret-value" not in result.text
        assert "second-secret-value" not in result.text
        assert result.text.endswith("***")

    @pytest.mark.parametrize("serialization_depth", range(4))
    @pytest.mark.parametrize(
        "key",
        [
            "api_key",
            "access_key",
            "private_key",
            "client_secret",
            "access_token",
            "refresh_token",
            "password",
            "passwd",
            "secret",
            "token",
        ],
    )
    def test_serialized_unicode_credential_keys_are_redacted(
        self,
        serialization_depth,
        key,
    ):
        escaped_key = "".join(f"\\u{ord(character):04x}" for character in key)
        value = f'{{"{escaped_key}":{{"inner":"LEAKME"}},"timeout":30}}'
        for _ in range(serialization_depth):
            value = json.dumps(value)[1:-1]

        result = redact_ci_sink(value)

        assert "LEAKME" not in result.text
        assert "timeout" in result.text
        assert result.reasons == ("credential-assignment",)

    @pytest.mark.parametrize(
        "secrets",
        [
            ("abcdefgh", "abcdefghXYZ"),
            ("abcdefghXYZ", "abcdefgh"),
        ],
    )
    def test_overlapping_environment_secrets_are_redacted_longest_first(self, secrets):
        result = redact_ci_sink("header=abcdefghXYZ", secret_values=secrets)

        assert result.text == "header=***"
        assert result.reasons == ("environment-secret",)

    def test_mixed_case_credential_assignments_are_redacted(self):
        escaped_key = "access" + "\\u005f" + "token"
        escaped_value = "prefix" + '\\"' + "suffix"
        escaped_json = '{\\"password\\":\\"escaped-json-value\\"}'
        value = (
            "ClIeNt_SeCrEt: opaque-value-123456\n"
            "API-KEY = 'quoted-secret-value'\n"
            'password: "quoted-password-value"\n'
            '{"access_token":"json-secret-value"}\n'
            f'{{"{escaped_key}":"short"}}\n'
            f'{{"password":"{escaped_value}"}}\n'
            "DB_PASSWORD=x\n"
            "GITHUB_TOKEN=y\n"
            f"{escaped_json}\n"
            'password="unterminated-secret-value\\"'
        )

        result = redact_ci_sink(value)

        assert "opaque-value-123456" not in result.text
        assert "quoted-secret-value" not in result.text
        assert "quoted-password-value" not in result.text
        assert "json-secret-value" not in result.text
        assert "short" not in result.text
        assert "prefix" not in result.text
        assert "suffix" not in result.text
        assert "escaped-json-value" not in result.text
        assert "unterminated-secret-value" not in result.text
        assert "DB_PASSWORD=***" in result.text
        assert "GITHUB_TOKEN=***" in result.text
        assert result.reasons.count("credential-assignment") == 10

    def test_credential_assignment_preserves_json_after_quoted_value(self):
        value = '{"password":"secret","timeout":30}'

        result = redact_ci_sink(value)

        assert result.text == '{"password":"***","timeout":30}'
        assert result.reasons == ("credential-assignment",)

    def test_credential_assignment_preserves_text_after_unquoted_value(self):
        value = "password=hunter2 other=1"

        result = redact_ci_sink(value)

        assert result.text == "password=*** other=1"
        assert result.reasons == ("credential-assignment",)

    def test_credential_assignment_handles_escaped_quote_inside_quoted_value(self):
        value = '{"password":"se\\"cret","x":1}'

        result = redact_ci_sink(value)

        assert result.text == '{"password":"***","x":1}'
        assert result.reasons == ("credential-assignment",)

    @pytest.mark.parametrize("boundary", [",", ", ", ";", "}", "]", " "])
    def test_escaped_json_inner_quote_at_boundary_cannot_leak_suffix(self, boundary):
        value = r"{\"password\":\"SECRET_PREFIX\\\"" + boundary + r"SECRET_SUFFIX\",\"timeout\":30}"

        result = redact_ci_sink(value)

        assert "SECRET_PREFIX" not in result.text
        assert "SECRET_SUFFIX" not in result.text
        assert r"\"timeout\":30}" in result.text

    def test_credential_assignment_handles_unterminated_quoted_value(self):
        value = '{"password":"secret'

        result = redact_ci_sink(value)

        assert result.text == '{"password":"***'
        assert result.reasons == ("credential-assignment",)

    def test_credential_assignment_redacts_multiple_secrets_on_one_line(self):
        value = "password=hunter2 token=secret123 other=1"

        result = redact_ci_sink(value)

        assert result.text == "password=*** token=*** other=1"
        assert result.reasons == ("credential-assignment", "credential-assignment")

    def test_credential_assignment_leaves_non_secret_line_byte_identical(self):
        value = '{"username":"alice","timeout":30} other=1'

        result = redact_ci_sink(value)

        assert result.text == value
        assert not result.redacted

    @pytest.mark.parametrize(
        ("serialized", "scheme", "credential"),
        [
            (False, "Token", "abc123xyz"),
            (False, "Basic", "dXNlcjpwYXNz"),
            (True, "Bear" + "er", "opaque-token-value"),
        ],
    )
    def test_structured_authorization_credentials_are_redacted(
        self,
        serialized,
        scheme,
        credential,
    ):
        value = f'{{"Authorization":"{scheme} {credential}","timeout":30}}'
        if serialized:
            value = value.replace('"', '\\"')

        result = redact_ci_sink(value)

        assert credential not in result.text
        assert "timeout" in result.text
        assert result.redacted

    def test_unicode_escaped_authorization_key_is_redacted(self):
        key = "\\u0041uthorization"
        credential = "ordinary-token-value"
        value = f'{{"{key}":"Token {credential}","timeout":30}}'

        result = redact_ci_sink(value)

        assert credential not in result.text
        assert "timeout" in result.text
        assert result.reasons == ("authorization-header",)

    def test_plain_authorization_header_uses_header_redactor_once(self):
        value = "Authorization: " + "Bear" + "er opaque-token-value"

        result = redact_ci_sink(value)

        assert result.text.endswith("***")
        assert result.reasons == ("authorization-header",)

    def test_authorization_word_without_credential_passes_through(self):
        value = "The authorization decision is documented in section 3."

        result = redact_ci_sink(value)

        assert result.text == value
        assert not result.redacted

    def test_source_profile_preserves_assignment_expressions(self):
        value = (
            "token = accept_unverified_jwt(user_input)\n"
            'password = response["password"]\n'
            "secret = payload.secret"
        )

        result = redact_ci_sink(value, redact_assignments=False)

        assert result.text == value
        assert not result.redacted

    def test_source_profile_still_redacts_installed_and_shaped_secrets(self):
        installed = "opaque-environment-value"
        shaped = f"ghp_{'A' * 36}"
        value = f"password={installed}\ntoken={shaped}"

        result = redact_ci_sink(
            value,
            secret_values=(installed,),
            redact_assignments=False,
        )

        assert installed not in result.text
        assert shaped not in result.text
        assert "***" in result.text
        assert "[redacted: github-token]" in result.text

    @pytest.mark.parametrize("serialization_depth", range(7))
    def test_source_profile_redacts_unicode_escaped_authorization(
        self,
        serialization_depth,
    ):
        credential = "ordinary-token-value"
        value = f'{{"\\u0041uthorization":"Token {credential}","timeout":30}}'
        for _ in range(serialization_depth):
            value = json.dumps(value)[1:-1]

        result = redact_ci_sink(value, redact_assignments=False)

        assert credential not in result.text
        assert "timeout" in result.text
        assert result.reasons == ("authorization-header",)

    def test_credential_assignment_scanner_avoids_quadratic_scaling(self):
        line = "ordinary_name = ordinary_value\n"
        value = (line * (32 * 1024 // len(line) + 1))[: 32 * 1024]

        started = time.perf_counter()
        result = redact_ci_sink(value)
        elapsed = time.perf_counter() - started

        assert result.text == value
        assert elapsed < 5

    @pytest.mark.parametrize(
        "key",
        [
            "githubToken",
            "npmToken",
            "slackToken",
            "userPassword",
            "webhookSecret",
            "dbpassword",
            "mytoken",
            "a_b_c_d_e_f_g_h_i_token",
            f"{'a' * 256}_token",
        ],
    )
    def test_credential_assignment_redacts_unbounded_namespaces(self, key):
        value = f'{{"{key}":"SECRET_VALUE","timeout":30}}'

        result = redact_ci_sink(value)

        assert result.text == f'{{"{key}":"***","timeout":30}}'
        assert result.reasons == ("credential-assignment",)

    @pytest.mark.parametrize(
        "separator",
        ["-", "_", " ", r"\u0020", r"\u002d", r"\u005f", "\\"],
    )
    def test_credential_assignment_scanner_rejects_separator_redos(self, separator):
        value = f"ordinary{separator * (64 * 1024)}prose"

        started = time.perf_counter()
        result = redact_ci_sink(value)
        elapsed = time.perf_counter() - started

        assert result.text == value
        # Pre-push runs share CPU across parallel jobs. This matches the sibling
        # hostile-input budget while still rejecting a superlinear 64 KiB scan.
        assert elapsed < 5

    def test_credential_assignments_preserve_trailing_structured_fields(self):
        raw_json = '{"password":"secret","timeout":30}'
        escaped_json = '{\\"password\\":\\"secret\\",\\"timeout\\":30}'
        escaped_inner_quote = '{\\"password\\":\\"alpha' + ("\\" * 3) + '"beta\\",\\"timeout\\":30}'
        prose = "token=secret, mode=review"

        result = redact_ci_sink("\n".join((raw_json, escaped_json, escaped_inner_quote, prose)))

        assert '{"password":"***","timeout":30}' in result.text
        assert '{\\"password\\":\\"***\\",\\"timeout\\":30}' in result.text
        assert "token=***, mode=review" in result.text
        assert "alpha" not in result.text
        assert "beta" not in result.text
        assert "secret" not in result.text

    @pytest.mark.parametrize("backslash_count", range(1, 7))
    @pytest.mark.parametrize(
        ("prefix", "quote"),
        [
            ('{"password":', '"'),
            ('{\\"password\\":', '\\"'),
        ],
    )
    def test_quoted_assignment_inner_quotes_cannot_leak_suffix(
        self,
        backslash_count,
        prefix,
        quote,
    ):
        value = (
            prefix
            + quote
            + "SECRET_PREFIX"
            + ("\\" * backslash_count)
            + '"SECRET_SUFFIX'
            + quote
            + ',"timeout":30}'
        )

        result = redact_ci_sink(value)

        assert "SECRET_PREFIX" not in result.text
        assert "SECRET_SUFFIX" not in result.text
        assert '"timeout":30}' in result.text


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
