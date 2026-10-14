"""Tests for github_core.not_found.is_pr_not_found (issue #6163)."""

from __future__ import annotations

import pytest

from scripts import github_core
from scripts.github_core.not_found import is_pr_not_found


class TestIsPrNotFound:
    @pytest.mark.parametrize(
        "text",
        [
            "not found",
            "gh: Not Found (HTTP 404)",
            "NOT FOUND",
            "GraphQL: Could not resolve to a PullRequest with the number of 50.",
            "graphql: could not resolve to a pullrequest with the number of 50.",
            "COULD NOT RESOLVE TO A PULLREQUEST",
            "stdout noise\nGraphQL: Could not resolve to a PullRequest\nmore",
            "Could not resolve not found",
        ],
    )
    def test_missing_pr_wordings_match(self, text):
        assert is_pr_not_found(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "internal server error",
            "HTTP 500",
            "not logged in",
            "Could not resolve host: api.github.com",
            "GraphQL: Could not resolve to a Repository with the name 'o/r'.",
            "Resource not accessible by integration (HTTP 403)",
            "timeout",
        ],
    )
    def test_other_failures_do_not_match(self, text):
        assert is_pr_not_found(text) is False

    @pytest.mark.parametrize("text", [None, ""])
    def test_empty_input_is_false(self, text):
        assert is_pr_not_found(text) is False

    def test_exported_from_package(self):
        assert github_core.is_pr_not_found is is_pr_not_found
        assert "is_pr_not_found" in github_core.__all__
