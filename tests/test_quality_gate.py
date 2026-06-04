"""Tests for quality-gate failure categorization and spec validation.

Split from test_ai_review.py (issue #1963). Covers get_failure_category and
spec_validation_failed. Moved verbatim; behavior unchanged.
"""

from __future__ import annotations

from scripts.ai_review_common import (
    get_failure_category,
    spec_validation_failed,
)

# ---------------------------------------------------------------------------
# Failure categorization
# ---------------------------------------------------------------------------


class TestGetFailureCategory:
    def test_exit_code_124_is_infrastructure(self):
        assert get_failure_category(exit_code=124) == "INFRASTRUCTURE"

    def test_exit_code_124_overrides_message(self):
        assert (
            get_failure_category(exit_code=124, message="Security vulnerability detected")
            == "INFRASTRUCTURE"
        )

    def test_rate_limit_message(self):
        assert get_failure_category(message="rate limit exceeded") == "INFRASTRUCTURE"

    def test_ratelimit_no_space(self):
        assert get_failure_category(message="API ratelimit hit") == "INFRASTRUCTURE"

    def test_timeout_message(self):
        assert get_failure_category(message="Request timed out") == "INFRASTRUCTURE"

    def test_429_error(self):
        assert get_failure_category(message="HTTP 429 Too Many Requests") == "INFRASTRUCTURE"

    def test_network_error(self):
        assert get_failure_category(message="network error connecting to API") == "INFRASTRUCTURE"

    def test_502_bad_gateway(self):
        assert get_failure_category(stderr="502 Bad Gateway") == "INFRASTRUCTURE"

    def test_503_service_unavailable(self):
        assert get_failure_category(stderr="503 Service Unavailable") == "INFRASTRUCTURE"

    def test_connection_refused(self):
        assert get_failure_category(stderr="connection refused") == "INFRASTRUCTURE"

    def test_connection_reset(self):
        assert get_failure_category(stderr="connection reset by peer") == "INFRASTRUCTURE"

    def test_connection_timeout(self):
        assert get_failure_category(stderr="connection timeout") == "INFRASTRUCTURE"

    def test_copilot_cli_no_output(self):
        assert (
            get_failure_category(message="Copilot CLI failed (exit code 1) with no output")
            == "INFRASTRUCTURE"
        )

    def test_missing_copilot_access(self):
        assert (
            get_failure_category(message="missing Copilot access for the bot account")
            == "INFRASTRUCTURE"
        )

    def test_insufficient_scopes(self):
        assert (
            get_failure_category(message="insufficient scopes for this operation")
            == "INFRASTRUCTURE"
        )

    def test_empty_output_is_infrastructure(self):
        assert get_failure_category(message="", stderr="") == "INFRASTRUCTURE"

    def test_no_args_is_infrastructure(self):
        assert get_failure_category() == "INFRASTRUCTURE"

    def test_security_vulnerability_is_code_quality(self):
        assert (
            get_failure_category(message="Security vulnerability detected in dependencies")
            == "CODE_QUALITY"
        )

    def test_code_quality_failure(self):
        msg = "VERDICT: CRITICAL_FAIL - Code does not meet quality standards"
        assert get_failure_category(message=msg) == "CODE_QUALITY"

    def test_test_failure(self):
        assert (
            get_failure_category(message="Tests failed: 3 assertions did not pass")
            == "CODE_QUALITY"
        )

    def test_missing_docs_is_code_quality(self):
        assert (
            get_failure_category(message="Missing documentation for public API")
            == "CODE_QUALITY"
        )

    def test_message_checked_before_stderr(self):
        assert (
            get_failure_category(message="rate limit exceeded", stderr="")
            == "INFRASTRUCTURE"
        )

    def test_stderr_checked_when_message_no_match(self):
        assert (
            get_failure_category(message="Some unrelated message", stderr="503 Service Unavailable")
            == "INFRASTRUCTURE"
        )

    def test_case_insensitive(self):
        assert get_failure_category(message="RATE LIMIT EXCEEDED") == "INFRASTRUCTURE"
        assert get_failure_category(message="Rate Limit") == "INFRASTRUCTURE"
# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------


class TestSpecValidationFailed:
    def test_trace_critical_fail(self):
        assert spec_validation_failed("CRITICAL_FAIL", "PASS") is True

    def test_trace_fail(self):
        assert spec_validation_failed("FAIL", "PASS") is True

    def test_trace_needs_review(self):
        assert spec_validation_failed("NEEDS_REVIEW", "PASS") is True

    def test_completeness_critical_fail(self):
        assert spec_validation_failed("PASS", "CRITICAL_FAIL") is True

    def test_completeness_fail(self):
        assert spec_validation_failed("PASS", "FAIL") is True

    def test_completeness_partial(self):
        assert spec_validation_failed("PASS", "PARTIAL") is True

    def test_completeness_needs_review(self):
        assert spec_validation_failed("PASS", "NEEDS_REVIEW") is True

    def test_both_pass(self):
        assert spec_validation_failed("PASS", "PASS") is False

    def test_trace_warn_completeness_pass(self):
        assert spec_validation_failed("WARN", "PASS") is False

    def test_trace_pass_completeness_warn(self):
        assert spec_validation_failed("PASS", "WARN") is False

    def test_both_warn(self):
        assert spec_validation_failed("WARN", "WARN") is False

    def test_both_fail(self):
        assert spec_validation_failed("FAIL", "FAIL") is True

    def test_warn_with_partial(self):
        assert spec_validation_failed("WARN", "PARTIAL") is True

    def test_empty_verdicts(self):
        assert spec_validation_failed("", "") is False

    def test_unknown_verdicts(self):
        assert spec_validation_failed("UNKNOWN", "UNKNOWN") is False

    def test_case_insensitive(self):
        assert spec_validation_failed("fail", "pass") is True
        assert spec_validation_failed("FAIL", "PASS") is True
        assert spec_validation_failed("Fail", "Pass") is True

    def test_trace_failure_with_completeness_pass(self):
        assert spec_validation_failed("CRITICAL_FAIL", "PASS") is True

    def test_completeness_failure_with_trace_pass(self):
        assert spec_validation_failed("PASS", "CRITICAL_FAIL") is True
