"""Tests for the GitHub-authoritative closing-link check (issue #3827).

`validate_closing_links` models how GitHub parses a closing keyword. These
tests cover the check that asks GitHub instead: each active claim in the body
must appear in the pull request's ``closingIssuesReferences``.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.validation import pr_description as mod
from scripts.validation.pr_description import (
    extract_active_closing_claims,
    fetch_closing_references,
    validate_closing_links,
    validate_closing_links_against_github,
)

_RUN = "scripts.validation.pr_description.subprocess.run"
_FETCH = "scripts.validation.pr_description.fetch_closing_references"


def _graphql(nodes: list[tuple[str, int]], total: int | None = None) -> MagicMock:
    payload: dict[str, Any] = {
        "data": {
            "repository": {
                "pullRequest": {
                    "closingIssuesReferences": {
                        "totalCount": len(nodes) if total is None else total,
                        "nodes": [
                            {"number": n, "repository": {"nameWithOwner": repo}}
                            for repo, n in nodes
                        ],
                    }
                }
            }
        }
    }
    return MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")


class TestExtractActiveClosingClaims:
    def test_bare_claim_targets_this_repository(self) -> None:
        assert extract_active_closing_claims("Fixes #12\n", "O", "R") == {("o/r", 12): "#12"}

    def test_cross_repo_claim_keeps_its_repository(self) -> None:
        claims = extract_active_closing_claims("Closes Other/Repo#5", "o", "r")
        assert claims == {("other/repo", 5): "Other/Repo#5"}

    def test_same_issue_twice_is_one_claim(self) -> None:
        body = "Fixes #7\nResolves o/r#7\n"
        assert extract_active_closing_claims(body, "o", "r") == {("o/r", 7): "#7"}

    @pytest.mark.parametrize(
        "body",
        [
            "`Fixes #3`",
            "``Fixes #3``",
            "```\nFixes #3\n```\n",
            "<!-- Fixes #3 -->",
            '<!--\n- Issues: "Closes #3"\n-->',
            "<!-- unclosed comment hides the rest\nFixes #3\n",
            "Refs #3",
            "Fixes \\#3",
        ],
    )
    def test_hidden_or_non_closing_text_is_not_a_claim(self, body: str) -> None:
        assert extract_active_closing_claims(body, "o", "r") == {}

    def test_claim_after_a_closed_comment_is_active(self) -> None:
        body = "<!-- Fixes #1 -->\nFixes #2\n"
        assert set(extract_active_closing_claims(body, "o", "r")) == {("o/r", 2)}

    def test_comment_opener_inside_code_is_literal_text(self) -> None:
        body = "Use `<!--` to start a comment.\n\nFixes #9\n"
        assert set(extract_active_closing_claims(body, "o", "r")) == {("o/r", 9)}

    def test_crlf_body_is_normalized(self) -> None:
        body = "```\r\nFixes #1\r\n```\r\nFixes #2\r\n"
        assert set(extract_active_closing_claims(body, "o", "r")) == {("o/r", 2)}


class TestHtmlCommentInRegexCheck:
    """The template ships example keywords inside comments; they are not claims."""

    def test_comment_keyword_on_stacked_pr_warns_nothing(self) -> None:
        body = "<!-- Link related issues: Fixes #123, Closes #456 -->\n"
        assert validate_closing_links(body, "stack", "main") == []

    def test_code_span_inside_comment_is_not_critical(self) -> None:
        assert validate_closing_links("<!-- `Fixes #1` -->", "main", "main") == []


class TestFetchClosingReferences:
    @patch(_RUN)
    def test_returns_lowercased_targets(self, run: MagicMock) -> None:
        run.return_value = _graphql([("O/R", 4), ("x/y", 5)])
        assert fetch_closing_references(9, "O", "R") == {("o/r", 4), ("x/y", 5)}

    @patch(_RUN)
    def test_sends_typed_variables(self, run: MagicMock) -> None:
        run.return_value = _graphql([])
        fetch_closing_references(9, "own", "rep")
        argv = run.call_args[0][0]
        assert argv[:3] == ["gh", "api", "graphql"]
        assert "owner=own" in argv and "name=rep" in argv
        assert argv[argv.index("number=9") - 1] == "-F"
        assert run.call_args.kwargs["timeout"] == 30

    @patch(_RUN)
    def test_nonzero_exit_raises_with_stderr(self, run: MagicMock) -> None:
        run.return_value = MagicMock(returncode=1, stdout="", stderr="HTTP 401\n")
        with pytest.raises(RuntimeError, match="HTTP 401"):
            fetch_closing_references(1, "o", "r")

    @pytest.mark.parametrize(
        "stdout",
        [
            "not json",
            json.dumps({"data": {"repository": {"pullRequest": None}}}),
            json.dumps({"errors": [{"message": "x"}]}),
        ],
    )
    @patch(_RUN)
    def test_unexpected_shape_raises(self, run: MagicMock, stdout: str) -> None:
        run.return_value = MagicMock(returncode=0, stdout=stdout, stderr="")
        with pytest.raises(RuntimeError, match="unexpected shape"):
            fetch_closing_references(1, "o", "r")

    @patch(_RUN)
    def test_truncated_answer_raises(self, run: MagicMock) -> None:
        run.return_value = _graphql([("o/r", 1)], total=101)
        with pytest.raises(RuntimeError, match="1 of 101"):
            fetch_closing_references(1, "o", "r")

    @pytest.mark.parametrize(
        ("error", "match"),
        [
            (FileNotFoundError(), "gh CLI not found"),
            (subprocess.TimeoutExpired(cmd="gh", timeout=30), "timed out"),
        ],
    )
    @patch(_RUN)
    def test_process_errors_raise(self, run: MagicMock, error: Exception, match: str) -> None:
        run.side_effect = error
        with pytest.raises(RuntimeError, match=match):
            fetch_closing_references(1, "o", "r")


class TestValidateAgainstGitHub:
    def _check(self, body: str, base: str = "main") -> list[mod.Issue]:
        return validate_closing_links_against_github(3, "o", "r", body, base, "main")

    @patch(_FETCH, return_value={("o/r", 1), ("o/r", 2)})
    def test_every_claim_linked_passes(self, fetch: MagicMock) -> None:
        assert self._check("Fixes #1\nCloses #2\n") == []
        fetch.assert_called_once_with(3, "o", "r")

    @patch(_FETCH, return_value={("o/r", 1)})
    def test_unlinked_claim_is_critical(self, fetch: MagicMock) -> None:
        issues = self._check("Fixes #1\nFixes #2\n")
        assert [(i.severity, i.issue_type) for i in issues] == [
            ("CRITICAL", "Closing keyword not linked by GitHub")
        ]
        assert "#2" in issues[0].message
        assert "Fixes #2" in issues[0].message

    @patch(_FETCH, return_value={("o/r", 5)})
    def test_cross_repo_claim_needs_its_own_link(self, fetch: MagicMock) -> None:
        issues = self._check("Fixes other/repo#5\n")
        assert len(issues) == 1
        assert "other/repo#5" in issues[0].message

    @patch(_FETCH, return_value={("o/r", 1), ("o/r", 99)})
    def test_link_without_claim_passes(self, fetch: MagicMock) -> None:
        """A sidebar link closes an issue too; only unmet claims fail."""
        assert self._check("Fixes #1\n") == []

    @patch(_FETCH)
    def test_no_active_claim_skips_the_query(self, fetch: MagicMock) -> None:
        assert self._check("Refs #1\n<!-- Fixes #2 -->\n`Fixes #3`\n") == []
        fetch.assert_not_called()

    @patch(_FETCH)
    def test_non_default_base_skips_the_query(self, fetch: MagicMock) -> None:
        assert self._check("Fixes #1\n", base="stack") == []
        fetch.assert_not_called()

    @patch(_FETCH, side_effect=RuntimeError("HTTP 401"))
    def test_unreadable_links_warn_and_never_pass_silently(self, fetch: MagicMock) -> None:
        issues = self._check("Fixes #1\n")
        assert [(i.severity, i.issue_type) for i in issues] == [
            ("WARNING", "Closing links not verified")
        ]
        assert "HTTP 401" in issues[0].message


class TestMainWiring:
    @patch(_FETCH, return_value=set())
    @patch("scripts.validation.pr_description.fetch_pr_data")
    def test_unlinked_claim_fails_ci(self, fetch_pr: MagicMock, fetch_refs: MagicMock) -> None:
        fetch_pr.return_value = {
            "title": "fix: x",
            "body": "Fixes #7\n",
            "files": [],
            "labels": [],
            "base_ref": "main",
            "default_branch": "main",
        }
        assert mod.main(["--pr-number", "4", "--owner", "o", "--repo", "r", "--ci"]) == 1
        fetch_refs.assert_called_once_with(4, "o", "r")

    @patch(_FETCH, return_value={("o/r", 7)})
    @patch("scripts.validation.pr_description.fetch_pr_data")
    def test_linked_claim_passes_ci(self, fetch_pr: MagicMock, fetch_refs: MagicMock) -> None:
        fetch_pr.return_value = {
            "title": "fix: x",
            "body": "Fixes #7\n",
            "files": [],
            "labels": [],
            "base_ref": "main",
            "default_branch": "main",
        }
        assert mod.main(["--pr-number", "4", "--owner", "o", "--repo", "r", "--ci"]) == 0
