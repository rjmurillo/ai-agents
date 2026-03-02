"""Tests for extract_github_context.py."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "extract_github_context"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestExtractGitHubContext:
    def test_pr_url(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context(
            "Check https://github.com/owner/repo/pull/123"
        )
        assert 123 in result["PRNumbers"]
        assert result["Owner"] == "owner"
        assert result["Repo"] == "repo"

    def test_issue_url(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context(
            "See https://github.com/org/project/issues/456"
        )
        assert 456 in result["IssueNumbers"]
        assert result["Owner"] == "org"
        assert result["Repo"] == "project"

    def test_pr_text_pattern(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context("Review PR 806 comments")
        assert 806 in result["PRNumbers"]

    def test_pr_hash_pattern(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context("Review PR #42")
        assert 42 in result["PRNumbers"]

    def test_pull_request_pattern(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context("Check pull request 99")
        assert 99 in result["PRNumbers"]

    def test_issue_text_pattern(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context("Fix issue #45")
        assert 45 in result["IssueNumbers"]

    def test_issues_plural(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context("See issues 10")
        assert 10 in result["IssueNumbers"]

    def test_standalone_hash(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context("Fix #100")
        assert 100 in result["PRNumbers"]

    def test_multiple_urls(self, _import_module):
        mod = _import_module
        text = (
            "https://github.com/a/b/pull/1 and "
            "https://github.com/a/b/issues/2"
        )
        result = mod.extract_github_context(text)
        assert 1 in result["PRNumbers"]
        assert 2 in result["IssueNumbers"]

    def test_no_duplicates(self, _import_module):
        mod = _import_module
        text = "PR 5 and PR #5 again"
        result = mod.extract_github_context(text)
        assert result["PRNumbers"].count(5) == 1

    def test_require_pr_exits_1(self, _import_module):
        mod = _import_module
        with pytest.raises(SystemExit) as exc:
            mod.extract_github_context(
                "no numbers here", require_pr=True,
            )
        assert exc.value.code == 1

    def test_require_issue_exits_1(self, _import_module):
        mod = _import_module
        with pytest.raises(SystemExit) as exc:
            mod.extract_github_context(
                "no numbers here", require_issue=True,
            )
        assert exc.value.code == 1

    def test_empty_text(self, _import_module):
        mod = _import_module
        result = mod.extract_github_context("")
        assert result["PRNumbers"] == []
        assert result["IssueNumbers"] == []
        assert result["Owner"] is None

    def test_hash_inside_url_not_duplicated(self, _import_module):
        mod = _import_module
        text = "https://github.com/o/r/pull/42 is good"
        result = mod.extract_github_context(text)
        assert result["PRNumbers"] == [42]
