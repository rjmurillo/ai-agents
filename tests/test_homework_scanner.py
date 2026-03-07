"""Tests for homework_scanner.py.

Tests cover pattern matching, false positive filtering, excerpt extraction,
repo string parsing, issue body building, and the main CLI entry point.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.homework_scanner import (
    FALSE_POSITIVE_PATTERNS,
    HOMEWORK_PATTERNS,
    HomeworkItem,
    ScanResult,
    build_issue_body,
    create_issues,
    extract_excerpt,
    find_homework_in_text,
    is_false_positive,
    main,
    parse_repo_string,
    scan_pr,
)

# --- Pattern matching tests ---


class TestFindHomeworkInText:
    """Tests for find_homework_in_text."""

    @pytest.mark.parametrize(
        "text",
        [
            "Deferred to follow-up: extract duplicated logic",
            "This is a future improvement we should consider",
            "A future improvement could be adding caching",
            "This is out of scope for this PR",
            "Will be addressed in a future PR",
            "This is a follow-up task for later",
            "TODO: refactor this function",
        ],
    )
    def test_detects_homework_patterns(self, text: str) -> None:
        result = find_homework_in_text(text)
        assert result is not None, f"Expected match for: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "Looks good to me",
            "LGTM, no changes needed",
            "Nice refactor!",
            "This is working as expected",
            "",
        ],
    )
    def test_no_match_for_normal_comments(self, text: str) -> None:
        assert find_homework_in_text(text) is None


class TestIsFalsePositive:
    """Tests for is_false_positive."""

    def test_bot_failure_todo_is_false_positive(self) -> None:
        assert is_false_positive("TODO in bot failure message was ignored")

    def test_nitpick_addressed_is_false_positive(self) -> None:
        assert is_false_positive("nitpick was already addressed in commit abc")

    def test_quoted_todo_is_false_positive(self) -> None:
        assert is_false_positive("  > TODO: this is quoted")

    def test_real_homework_is_not_false_positive(self) -> None:
        assert not is_false_positive("Deferred to follow-up: fix the bug")

    def test_empty_string_is_not_false_positive(self) -> None:
        assert not is_false_positive("")


# --- Excerpt extraction tests ---


class TestExtractExcerpt:
    """Tests for extract_excerpt."""

    def test_short_text_unchanged(self) -> None:
        assert extract_excerpt("short text") == "short text"

    def test_long_text_truncated(self) -> None:
        long_text = "a" * 300
        result = extract_excerpt(long_text)
        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")

    def test_whitespace_collapsed(self) -> None:
        assert extract_excerpt("hello\n  world\n\n  foo") == "hello world foo"

    def test_custom_max_length(self) -> None:
        result = extract_excerpt("abcdefghij", max_length=5)
        assert result == "abcde..."


# --- Repo parsing tests ---


class TestParseRepoString:
    """Tests for parse_repo_string."""

    def test_valid_repo(self) -> None:
        assert parse_repo_string("owner/repo") == ("owner", "repo")

    def test_invalid_no_slash(self) -> None:
        with pytest.raises(ValueError, match="Invalid repo format"):
            parse_repo_string("noslash")

    def test_invalid_too_many_slashes(self) -> None:
        with pytest.raises(ValueError, match="Invalid repo format"):
            parse_repo_string("a/b/c")


# --- Issue body building tests ---


class TestBuildIssueBody:
    """Tests for build_issue_body."""

    def test_contains_source_info(self) -> None:
        item = HomeworkItem(
            pr_number=42,
            comment_id=123,
            author="reviewer",
            body_excerpt="Deferred to follow-up: fix the bug",
            matched_pattern="deferred",
            comment_url="https://github.com/owner/repo/pull/42#discussion_r123",
            source_type="review_comment",
        )
        body = build_issue_body(item, "owner", "repo")
        assert "PR #42" in body
        assert "@reviewer" in body
        assert "https://github.com/owner/repo/pull/42#discussion_r123" in body
        assert "Deferred to follow-up: fix the bug" in body
        assert "Homework Scanner" in body


# --- Scan PR tests ---


class TestScanPr:
    """Tests for scan_pr with mocked GitHub API calls."""

    @patch("scripts.homework_scanner.fetch_pr_comments")
    def test_scan_finds_homework_in_review_comments(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = (
            [
                {
                    "id": 1,
                    "body": "Deferred to follow-up: extract shared logic",
                    "user": {"login": "reviewer1"},
                    "html_url": "https://github.com/o/r/pull/1#discussion_r1",
                }
            ],
            [],
        )
        result = scan_pr("o", "r", 1)
        assert len(result.items) == 1
        assert result.items[0].source_type == "review_comment"
        assert result.comments_scanned == 1

    @patch("scripts.homework_scanner.fetch_pr_comments")
    def test_scan_finds_homework_in_review_bodies(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = (
            [],
            [
                {
                    "id": 2,
                    "body": "TODO: add integration tests for edge cases",
                    "user": {"login": "reviewer2"},
                    "html_url": "https://github.com/o/r/pull/1#pullrequestreview-2",
                }
            ],
        )
        result = scan_pr("o", "r", 1)
        assert len(result.items) == 1
        assert result.items[0].source_type == "review_body"

    @patch("scripts.homework_scanner.fetch_pr_comments")
    def test_scan_filters_false_positives(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = (
            [
                {
                    "id": 3,
                    "body": "TODO in bot failure message was ignored",
                    "user": {"login": "bot"},
                    "html_url": "https://github.com/o/r/pull/1#discussion_r3",
                }
            ],
            [],
        )
        result = scan_pr("o", "r", 1)
        assert len(result.items) == 0
        assert result.comments_scanned == 1

    @patch("scripts.homework_scanner.fetch_pr_comments")
    def test_scan_skips_empty_review_bodies(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = (
            [],
            [
                {"id": 4, "body": "", "user": {"login": "r"}, "html_url": ""},
                {
                    "id": 5,
                    "body": "None",
                    "user": {"login": "r"},
                    "html_url": "",
                },
            ],
        )
        result = scan_pr("o", "r", 1)
        assert len(result.items) == 0
        assert result.comments_scanned == 0

    @patch("scripts.homework_scanner.fetch_pr_comments")
    def test_scan_handles_api_error(self, mock_fetch: MagicMock) -> None:
        mock_fetch.side_effect = RuntimeError("API rate limited")
        result = scan_pr("o", "r", 1)
        assert result.error == "API rate limited"
        assert len(result.items) == 0


# --- Create issues tests ---


class TestCreateIssues:
    """Tests for create_issues in dry-run mode."""

    def test_dry_run_produces_output(self) -> None:
        items = [
            HomeworkItem(
                pr_number=10,
                comment_id=100,
                author="dev",
                body_excerpt="Future improvement: add caching",
                matched_pattern="future",
                comment_url="https://github.com/o/r/pull/10#discussion_r100",
                source_type="review_comment",
            )
        ]
        created = create_issues(items, "o", "r", dry_run=True)
        assert len(created) == 1
        assert created[0]["dry_run"] is True
        assert "Homework:" in str(created[0]["title"])


# --- CLI main tests ---


class TestMain:
    """Tests for the main CLI entry point."""

    def test_missing_repo_returns_2(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = main(["--pr", "1"])
        assert result == 2

    def test_invalid_repo_format_returns_2(self) -> None:
        result = main(["--pr", "1", "--repo", "noslash"])
        assert result == 2

    @patch("scripts.homework_scanner.scan_pr")
    def test_api_error_returns_3(self, mock_scan: MagicMock) -> None:
        mock_scan.return_value = ScanResult(pr_number=1, error="API failed")
        result = main(["--pr", "1", "--repo", "o/r"])
        assert result == 3

    @patch("scripts.homework_scanner.create_issues")
    @patch("scripts.homework_scanner.scan_pr")
    def test_success_returns_0(
        self, mock_scan: MagicMock, mock_create: MagicMock
    ) -> None:
        mock_scan.return_value = ScanResult(
            pr_number=1, comments_scanned=5, items=[]
        )
        result = main(["--pr", "1", "--repo", "o/r"])
        assert result == 0
        mock_create.assert_not_called()

    @patch("scripts.homework_scanner.create_issues")
    @patch("scripts.homework_scanner.scan_pr")
    def test_items_found_creates_issues(
        self, mock_scan: MagicMock, mock_create: MagicMock
    ) -> None:
        item = HomeworkItem(
            pr_number=1,
            comment_id=1,
            author="dev",
            body_excerpt="TODO: fix",
            matched_pattern="TODO",
            comment_url="url",
            source_type="review_comment",
        )
        mock_scan.return_value = ScanResult(
            pr_number=1, comments_scanned=3, items=[item]
        )
        mock_create.return_value = [{"title": "Homework: TODO: fix", "url": "url"}]
        result = main(["--pr", "1", "--repo", "o/r"])
        assert result == 0
        mock_create.assert_called_once()

    @patch("scripts.homework_scanner.create_issues")
    @patch("scripts.homework_scanner.scan_pr")
    def test_output_file_written(
        self, mock_scan: MagicMock, mock_create: MagicMock, tmp_path
    ) -> None:
        mock_scan.return_value = ScanResult(
            pr_number=1, comments_scanned=2, items=[]
        )
        out_file = tmp_path / "results.json"
        result = main(["--pr", "1", "--repo", "o/r", "--output", str(out_file)])
        assert result == 0
        data = json.loads(out_file.read_text())
        assert data["pr_number"] == 1
        assert data["items_found"] == 0


# --- Pattern coverage tests ---


class TestPatternCoverage:
    """Ensure all defined patterns have at least one test case."""

    def test_all_homework_patterns_have_coverage(self) -> None:
        test_inputs = [
            "Deferred to follow-up: do X",
            "future improvement here",
            "A future improvement could be Y",
            "out of scope for this PR",
            "addressed in a future PR",
            "follow-up task: do Z",
            "TODO: fix this",
        ]
        for i, pattern in enumerate(HOMEWORK_PATTERNS):
            assert pattern.search(
                test_inputs[i]
            ), f"Pattern {pattern.pattern} not matched by test input {i}"

    def test_all_false_positive_patterns_have_coverage(self) -> None:
        test_inputs = [
            "TODO in bot failure case",
            "nitpick was already addressed",
            "  > TODO: quoted",
            "```TODO: in code```",
        ]
        for i, pattern in enumerate(FALSE_POSITIVE_PATTERNS):
            assert pattern.search(
                test_inputs[i]
            ), f"FP pattern {pattern.pattern} not matched by test input {i}"
