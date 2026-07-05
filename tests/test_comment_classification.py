"""Unit tests for the shared comment-domain classifier (Issue #2816).

Covers the single-source-of-truth ``classify_domain`` extracted from the two
PR-comment skill scripts into ``scripts/github_core/comment_classification.py``.
"""

from __future__ import annotations

import pytest

from scripts.github_core.comment_classification import classify_domain


class TestClassifyDomainSecurity:
    @pytest.mark.parametrize(
        "body",
        [
            "CWE-22 path traversal found",
            "This is a SQL injection vulnerability",
            "Possible XSS in the render path",
            "Missing CSRF token check",
            "This weakens authentication",
            "authorization bypass here",
            "hard-coded credentials in the file",
            "secret token committed",
            "TOCTOU race on the symlink",
            "needs input sanitization",
            "must escape the user string",
        ],
    )
    def test_security(self, body: str) -> None:
        assert classify_domain(body) == "security"


class TestClassifyDomainBug:
    @pytest.mark.parametrize(
        "body",
        [
            "This throws error when empty",
            "the app crashes on startup",
            "unhandled exception here",
            "this fails when input is empty",
            "null pointer dereference",
            "undefined behavior in this path",
            "there is a race condition",
            "this deadlocks under load",
            "memory leak in the loop",
        ],
    )
    def test_bug(self, body: str) -> None:
        assert classify_domain(body) == "bug"


class TestClassifyDomainStyle:
    @pytest.mark.parametrize(
        "body",
        [
            "Fix the formatting and indentation",
            "Consider renaming this variable",
            "whitespace nit",
            "does not follow the naming convention",
            "improve readability here",
            "small cleanup / refactor",
        ],
    )
    def test_style(self, body: str) -> None:
        assert classify_domain(body) == "style"


class TestClassifyDomainSummary:
    @pytest.mark.parametrize(
        "body",
        [
            "## Summary\nOverview of changes",
            "# Overview",
            "### Walkthrough of the diff",
            "## Changes",
        ],
    )
    def test_summary(self, body: str) -> None:
        assert classify_domain(body) == "summary"


class TestClassifyDomainGeneral:
    @pytest.mark.parametrize("body", ["This looks good to me", "LGTM", "thanks!"])
    def test_general(self, body: str) -> None:
        assert classify_domain(body) == "general"

    @pytest.mark.parametrize("body", ["", "   ", "\n\t "])
    def test_empty_or_whitespace(self, body: str) -> None:
        assert classify_domain(body) == "general"

    @pytest.mark.parametrize("body", [None, 0, 123, ["security"], {"a": 1}])
    def test_non_string_returns_general(self, body: object) -> None:
        # Comment bodies come from an external API; a JSON null surfaces as
        # None. classify_domain must be total, never raising on such input.
        assert classify_domain(body) == "general"  # type: ignore[arg-type]


class TestClassifyDomainPrecedence:
    def test_security_beats_bug(self) -> None:
        # Body matches both bug ("crash") and security ("vulnerability");
        # security wins per the ordered checks.
        assert classify_domain("crash from a known vulnerability") == "security"

    def test_bug_beats_style(self) -> None:
        # Body matches both style ("refactor") and bug ("exception").
        assert classify_domain("refactor to stop the exception") == "bug"
