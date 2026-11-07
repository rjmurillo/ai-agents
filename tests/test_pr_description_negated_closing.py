"""Tests for validate_negated_closing_keywords in pr_description.py.

GitHub reads "does not close #N" as "close #N" and closes the issue on merge.
PR #7126 closed #5410 that way with a criterion unmet.

Covers:
- Positive: negated phrasings are flagged CRITICAL
- Negative: plain closing keywords, Refs, and "closing" (not a keyword) are not
- Edge: code spans, fences, HTML comments, sentence boundaries, CRLF, owner/repo
- Wiring: main() exits 1 in CI mode on a negated keyword
- Corpus: the repository PR template raises nothing
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.validation.pr_description import (
    RepoInfo,
    main,
    validate_negated_closing_keywords,
)

_TEMPLATE = Path(__file__).resolve().parents[1] / ".github" / "PULL_REQUEST_TEMPLATE.md"


def _types(body: str) -> list[str]:
    return [i.issue_type for i in validate_negated_closing_keywords(body)]


class TestNegatedPhrasesFlagged:
    @pytest.mark.parametrize(
        "body",
        [
            "This PR does not close #5410",
            "This PR doesn't fix #12",
            "This PR doesn’t fix #12",
            "It won't resolve #7.",
            "It will not close #7",
            "It did not fix #3",
            "It never closes #3",
            "It cannot resolve #3",
            "It no longer fixes #3",
            "This does not yet close #3",
            "This is not going to close #3",
            "This does NOT CLOSE #3",
            "This does not close other-org/other-repo#9",
            "Not closes #4",
        ],
    )
    def test_flags(self, body: str) -> None:
        assert _types(body) == ["Negated closing keyword"]

    def test_issue_is_critical_and_names_the_reference(self) -> None:
        [issue] = validate_negated_closing_keywords("It does not close org/repo#9.")
        assert issue.severity == "CRITICAL"
        assert issue.file == "<pr-body>"
        assert "org/repo#9" in issue.message
        assert "Refs org/repo#9" in issue.message

    def test_flags_each_negated_keyword(self) -> None:
        body = "It does not close #1.\nIt doesn't fix #2."
        assert len(validate_negated_closing_keywords(body)) == 2

    def test_crlf_body(self) -> None:
        assert _types("Intro.\r\nThis does not close #5\r\n") == ["Negated closing keyword"]


class TestNotFlagged:
    @pytest.mark.parametrize(
        "body",
        [
            "",
            "Closes #5410",
            "Fixes #12\nResolves #13",
            "Refs #5410",
            "This PR does not touch #5410",
            "This does not close the gap, but closes #5",
            "It is not done. Closes #5",
            "Not now: closes #5",
            "This PR is not closing #5",
            "No tests fail. Fixes #5",
            "knot closes #5",
            "Do not merge yet\n\nCloses #5",
        ],
    )
    def test_clean(self, body: str) -> None:
        assert validate_negated_closing_keywords(body) == []

    def test_negator_too_far_from_keyword(self) -> None:
        assert _types("It does not really need to be here so close #3") == []


class TestHiddenRegionsSkipped:
    def test_inline_code_span(self) -> None:
        assert _types("Write `does not close #5` carefully") == []

    def test_fenced_block(self) -> None:
        assert _types("```\nThis does not close #5\n```\n") == []

    def test_html_comment(self) -> None:
        assert _types("<!-- This does not close #5 -->") == []

    def test_template_style_comment_with_bare_keyword(self) -> None:
        assert _types("<!-- Closes #123 -->\nDoes not matter") == []

    def test_text_after_a_hidden_region_still_flagged(self) -> None:
        body = "<!-- note -->\nThis does not close #5"
        assert _types(body) == ["Negated closing keyword"]


class TestPullRequestTemplate:
    def test_template_raises_nothing(self) -> None:
        assert validate_negated_closing_keywords(_TEMPLATE.read_text(encoding="utf-8")) == []


class TestMainWiring:
    @patch("scripts.validation.pr_description.fetch_closing_references")
    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_ci_exits_one_on_negated_keyword(
        self, mock_repo: MagicMock, mock_fetch: MagicMock, mock_refs: MagicMock
    ) -> None:
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_refs.return_value = {("o/r", 5410)}
        mock_fetch.return_value = {
            "title": "Test",
            "body": "## Changes\nChanged `foo.py`\n\nThis PR does not close #5410",
            "files": [{"path": "foo.py"}],
            "base_ref": "main",
            "default_branch": "main",
        }
        assert main(["--pr-number", "1", "--ci"]) == 1

    @patch("scripts.validation.pr_description.fetch_closing_references")
    @patch("scripts.validation.pr_description.fetch_pr_data")
    @patch("scripts.validation.pr_description.get_repo_info")
    def test_ci_exits_zero_on_refs(
        self, mock_repo: MagicMock, mock_fetch: MagicMock, mock_refs: MagicMock
    ) -> None:
        mock_repo.return_value = RepoInfo(owner="o", repo="r")
        mock_refs.return_value = set()
        mock_fetch.return_value = {
            "title": "Test",
            "body": "## Changes\nChanged `foo.py`\n\nRefs #5410",
            "files": [{"path": "foo.py"}],
            "base_ref": "main",
            "default_branch": "main",
        }
        assert main(["--pr-number", "1", "--ci"]) == 0
