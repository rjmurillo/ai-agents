"""Tests for scripts.ci.failure_classification."""

from __future__ import annotations

import pytest

from scripts.ci.failure_classification import (
    FORK_PERMISSION_SIGNAL,
    RATE_LIMIT_SIGNAL,
    FailureClassification,
    classify_pr_fetch_failure,
)


class TestForkPermissionSignal:
    """FORK_PERMISSION_SIGNAL matches expected HTTP/permission patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "HTTP 403: Resource not accessible by integration",
            "HTTP 404: Not Found",
            "not accessible",
            "must have admin rights",
            "Could not resolve to a PullRequest",
            "http 403 forbidden",  # case-insensitive
        ],
    )
    def test_matches(self, text: str) -> None:
        assert FORK_PERMISSION_SIGNAL.search(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Everything is fine",
            "HTTP 200 OK",
            "timeout after 30 seconds",
            "",
        ],
    )
    def test_no_match(self, text: str) -> None:
        assert not FORK_PERMISSION_SIGNAL.search(text)


class TestRateLimitSignal:
    """RATE_LIMIT_SIGNAL matches rate-limit responses."""

    @pytest.mark.parametrize(
        "text",
        [
            "API rate limit exceeded",
            "secondary rate limit",
            "abuse detection mechanism",
            "RATE LIMIT hit",  # case-insensitive
        ],
    )
    def test_matches(self, text: str) -> None:
        assert RATE_LIMIT_SIGNAL.search(text)

    @pytest.mark.parametrize(
        "text",
        [
            "HTTP 403: Resource not accessible",
            "normal error",
            "",
        ],
    )
    def test_no_match(self, text: str) -> None:
        assert not RATE_LIMIT_SIGNAL.search(text)


class TestClassifyPrFetchFailure:
    """classify_pr_fetch_failure returns correct FailureClassification."""

    def test_plain_error(self) -> None:
        """Non-matching detail gets no hint."""
        result = classify_pr_fetch_failure("42", "connection timeout")
        assert isinstance(result, FailureClassification)
        assert result.hint == ""
        assert "connection timeout" in result.warning
        assert "connection timeout" in result.context_text
        assert "INFRASTRUCTURE_FAILURE" in result.context_text
        assert "42" in result.warning

    def test_fork_permission_hint(self) -> None:
        """HTTP 403 without rate-limit triggers the fork hint."""
        result = classify_pr_fetch_failure("99", "HTTP 403: Resource not accessible")
        assert "GH_TOKEN" in result.hint
        assert "GH_TOKEN" in result.warning
        assert "GH_TOKEN" in result.context_text

    def test_rate_limit_suppresses_fork_hint(self) -> None:
        """HTTP 403 + rate-limit text must NOT produce the fork hint (#4333)."""
        result = classify_pr_fetch_failure(
            "100", "HTTP 403: API rate limit exceeded"
        )
        assert result.hint == ""
        assert "GH_TOKEN" not in result.warning

    def test_empty_detail_gets_default(self) -> None:
        """Empty/whitespace detail normalises to a default message."""
        result = classify_pr_fetch_failure("1", "   ")
        assert result.detail == "GitHub API returned no diagnostic output"
        assert "GitHub API returned no diagnostic output" in result.warning

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped from detail."""
        result = classify_pr_fetch_failure("5", "  some error  ")
        assert result.detail == "some error"

    def test_context_text_prefix(self) -> None:
        """context_text always starts with INFRASTRUCTURE_FAILURE."""
        result = classify_pr_fetch_failure("7", "any error")
        assert result.context_text.startswith("INFRASTRUCTURE_FAILURE:")

    def test_warning_format(self) -> None:
        """warning uses the GitHub Actions annotation format."""
        result = classify_pr_fetch_failure("12", "oops")
        assert result.warning.startswith("::warning::")
