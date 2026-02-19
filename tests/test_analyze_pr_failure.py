"""Tests for scripts/analyze_pr_failure.py.

Covers all public functions and CLI paths:
- PR metadata fetch (success, not found, API error)
- Comment distribution (bot vs human classification)
- File distribution by directory
- Review timeline sorting
- Synthesis panel discovery
- Markdown and JSON output formats
- Argument parsing
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

import scripts.analyze_pr_failure as mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _pr_json(**overrides):
    """Build a realistic PR metadata response."""
    data = {
        "number": 908,
        "title": "Fix regression in auth module",
        "state": "MERGED",
        "author": {"login": "alice"},
        "createdAt": "2026-01-10T10:00:00Z",
        "updatedAt": "2026-01-12T15:00:00Z",
        "mergedAt": "2026-01-12T14:00:00Z",
        "additions": 150,
        "deletions": 30,
        "changedFiles": 8,
        "commits": [
            {"oid": "abc123"},
            {"oid": "def456"},
            {"oid": "ghi789"},
        ],
        "labels": [{"name": "bug"}, {"name": "priority:P1"}],
        "baseRefName": "main",
        "headRefName": "fix/auth-regression",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# _is_bot
# ---------------------------------------------------------------------------


class TestIsBot:
    def test_bot_suffix(self):
        assert mod._is_bot("dependabot[bot]") is True

    def test_bot_dash_suffix(self):
        assert mod._is_bot("rjmurillo-bot") is True

    def test_human(self):
        assert mod._is_bot("alice") is False

    def test_case_insensitive(self):
        assert mod._is_bot("MyApp[BOT]") is True


# ---------------------------------------------------------------------------
# build_comment_distribution
# ---------------------------------------------------------------------------


class TestBuildCommentDistribution:
    def test_empty(self):
        result = mod.build_comment_distribution([])
        assert result == {
            "total": 0,
            "bot_count": 0,
            "human_count": 0,
            "authors": {},
        }

    def test_mixed_authors(self):
        comments = [
            {"user": {"login": "alice"}},
            {"user": {"login": "bob"}},
            {"user": {"login": "coderabbit[bot]"}},
            {"user": {"login": "alice"}},
        ]
        result = mod.build_comment_distribution(comments)
        assert result["total"] == 4
        assert result["bot_count"] == 1
        assert result["human_count"] == 3
        assert result["authors"]["alice"] == 2
        assert result["authors"]["bob"] == 1


# ---------------------------------------------------------------------------
# build_file_distribution
# ---------------------------------------------------------------------------


class TestBuildFileDistribution:
    def test_empty(self):
        assert mod.build_file_distribution([]) == {}

    def test_groups_by_directory(self):
        files = [
            {"filename": "src/auth/login.py"},
            {"filename": "src/auth/logout.py"},
            {"filename": "tests/test_login.py"},
            {"filename": "README.md"},
        ]
        result = mod.build_file_distribution(files)
        assert result["src"] == 2
        assert result["tests"] == 1
        assert result["(root)"] == 1

    def test_nested_paths(self):
        files = [{"filename": "a/b/c/d.py"}]
        result = mod.build_file_distribution(files)
        assert result == {"a": 1}


# ---------------------------------------------------------------------------
# build_review_timeline
# ---------------------------------------------------------------------------


class TestBuildReviewTimeline:
    def test_empty(self):
        assert mod.build_review_timeline([]) == []

    def test_sorts_by_time(self):
        reviews = [
            {
                "user": {"login": "bob"},
                "state": "APPROVED",
                "submitted_at": "2026-01-12T14:00:00Z",
            },
            {
                "user": {"login": "alice"},
                "state": "CHANGES_REQUESTED",
                "submitted_at": "2026-01-11T10:00:00Z",
            },
        ]
        result = mod.build_review_timeline(reviews)
        assert result[0]["author"] == "alice"
        assert result[1]["author"] == "bob"

    def test_missing_user(self):
        reviews = [{"user": {}, "state": "COMMENTED", "submitted_at": "2026-01-11T10:00:00Z"}]
        result = mod.build_review_timeline(reviews)
        assert result[0]["author"] == "unknown"


# ---------------------------------------------------------------------------
# fetch_pr_metadata
# ---------------------------------------------------------------------------


class TestFetchPrMetadata:
    @patch("scripts.analyze_pr_failure._run_gh")
    def test_success(self, mock_gh):
        mock_gh.return_value = _completed(stdout=json.dumps(_pr_json()))
        result = mod.fetch_pr_metadata("owner", "repo", 908)
        assert result["number"] == 908

    @patch("scripts.analyze_pr_failure._run_gh")
    def test_not_found(self, mock_gh):
        mock_gh.return_value = _completed(stderr="not found", rc=1)
        with pytest.raises(SystemExit) as exc_info:
            mod.fetch_pr_metadata("owner", "repo", 999)
        assert exc_info.value.code == 2

    @patch("scripts.analyze_pr_failure._run_gh")
    def test_api_error(self, mock_gh):
        mock_gh.return_value = _completed(stderr="500 server error", rc=1)
        with pytest.raises(SystemExit) as exc_info:
            mod.fetch_pr_metadata("owner", "repo", 908)
        assert exc_info.value.code == 3


# ---------------------------------------------------------------------------
# fetch_pr_comments / fetch_pr_reviews / fetch_pr_files
# ---------------------------------------------------------------------------


class TestFetchHelpers:
    @patch("scripts.analyze_pr_failure._run_gh")
    def test_comments_success(self, mock_gh):
        mock_gh.return_value = _completed(stdout=json.dumps([{"id": 1}]))
        result = mod.fetch_pr_comments("owner", "repo", 1)
        assert len(result) == 1

    @patch("scripts.analyze_pr_failure._run_gh")
    def test_comments_failure(self, mock_gh):
        mock_gh.return_value = _completed(rc=1)
        assert mod.fetch_pr_comments("owner", "repo", 1) == []

    @patch("scripts.analyze_pr_failure._run_gh")
    def test_reviews_failure(self, mock_gh):
        mock_gh.return_value = _completed(rc=1)
        assert mod.fetch_pr_reviews("owner", "repo", 1) == []

    @patch("scripts.analyze_pr_failure._run_gh")
    def test_files_failure(self, mock_gh):
        mock_gh.return_value = _completed(rc=1)
        assert mod.fetch_pr_files("owner", "repo", 1) == []


# ---------------------------------------------------------------------------
# find_synthesis_panels
# ---------------------------------------------------------------------------


class TestFindSynthesisPanels:
    @patch("subprocess.run")
    def test_finds_panels(self, mock_run):
        mock_run.return_value = _completed(
            stdout=".agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md\n"
        )
        result = mod.find_synthesis_panels("owner", "repo", 908)
        assert len(result) >= 1
        assert "pr-908" in result[0]

    @patch("subprocess.run")
    def test_no_panels(self, mock_run):
        mock_run.return_value = _completed(stdout="")
        result = mod.find_synthesis_panels("owner", "repo", 1)
        assert result == []

    @patch("subprocess.run")
    def test_deduplicates(self, mock_run):
        mock_run.return_value = _completed(
            stdout=".agents/retrospective/pr-908-retro.md\n"
        )
        result = mod.find_synthesis_panels("owner", "repo", 908)
        # Both patterns may match same file; verify no duplicates
        assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# analyze_pr (integration-level with mocks)
# ---------------------------------------------------------------------------


class TestAnalyzePr:
    @patch("scripts.analyze_pr_failure.find_synthesis_panels", return_value=[])
    @patch("scripts.analyze_pr_failure.fetch_pr_files", return_value=[])
    @patch("scripts.analyze_pr_failure.fetch_pr_reviews", return_value=[])
    @patch("scripts.analyze_pr_failure.fetch_pr_comments", return_value=[])
    @patch("scripts.analyze_pr_failure.fetch_pr_metadata")
    def test_produces_complete_output(
        self, mock_meta, mock_comments, mock_reviews, mock_files, mock_panels,
    ):
        mock_meta.return_value = _pr_json()
        result = mod.analyze_pr("owner", "repo", 908)

        assert result["pr_number"] == 908
        assert result["title"] == "Fix regression in auth module"
        assert result["metrics"]["commits"] == 3
        assert result["metrics"]["additions"] == 150
        assert "comment_distribution" in result
        assert "file_distribution" in result
        assert "review_timeline" in result
        assert "synthesis_panels" in result


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------


class TestFormatMarkdown:
    def test_contains_title(self):
        analysis = {
            "pr_number": 908,
            "title": "Test PR",
            "state": "MERGED",
            "author": "alice",
            "base_branch": "main",
            "head_branch": "fix/test",
            "created_at": "2026-01-10",
            "updated_at": "2026-01-12",
            "merged_at": "2026-01-12",
            "labels": ["bug"],
            "metrics": {"commits": 3, "files_changed": 5, "additions": 100, "deletions": 20},
            "comment_distribution": {
                "total": 2, "bot_count": 1,
                "human_count": 1, "authors": {"alice": 1},
            },
            "file_distribution": {"src": 3, "tests": 2},
            "review_timeline": [
                {"author": "bob", "state": "APPROVED",
                 "submitted_at": "2026-01-11"},
            ],
            "synthesis_panels": [".agents/retrospective/pr-908-retro.md"],
        }
        md = mod.format_markdown(analysis)
        assert "# PR #908" in md
        assert "| Commits | 3 |" in md
        assert "| src | 3 |" in md
        assert "Synthesis Panels" in md

    def test_no_merged_at(self):
        analysis = {
            "pr_number": 1,
            "title": "Open PR",
            "state": "OPEN",
            "author": "alice",
            "base_branch": "main",
            "head_branch": "feat/x",
            "created_at": "2026-01-10",
            "updated_at": "2026-01-10",
            "merged_at": None,
            "labels": [],
            "metrics": {"commits": 1, "files_changed": 1, "additions": 5, "deletions": 0},
            "comment_distribution": {"total": 0, "bot_count": 0, "human_count": 0, "authors": {}},
            "file_distribution": {},
            "review_timeline": [],
            "synthesis_panels": [],
        }
        md = mod.format_markdown(analysis)
        assert "Merged" not in md


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------


class TestMain:
    @patch("scripts.analyze_pr_failure.analyze_pr")
    @patch("scripts.analyze_pr_failure._resolve_repo", return_value=("owner", "repo"))
    def test_json_output(self, mock_resolve, mock_analyze, capsys):
        mock_analyze.return_value = {"pr_number": 1, "title": "Test"}
        rc = mod.main(["--pr", "1"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["pr_number"] == 1

    @patch("scripts.analyze_pr_failure.analyze_pr")
    @patch("scripts.analyze_pr_failure._resolve_repo", return_value=("owner", "repo"))
    def test_markdown_output(self, mock_resolve, mock_analyze, capsys):
        mock_analyze.return_value = {
            "pr_number": 1,
            "title": "Test",
            "state": "OPEN",
            "author": "alice",
            "base_branch": "main",
            "head_branch": "feat/x",
            "created_at": "2026-01-10",
            "updated_at": "2026-01-10",
            "merged_at": None,
            "labels": [],
            "metrics": {"commits": 1, "files_changed": 1, "additions": 5, "deletions": 0},
            "comment_distribution": {"total": 0, "bot_count": 0, "human_count": 0, "authors": {}},
            "file_distribution": {},
            "review_timeline": [],
            "synthesis_panels": [],
        }
        rc = mod.main(["--pr", "1", "--format", "markdown"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "# PR #1" in output

    def test_missing_pr_arg(self):
        with pytest.raises(SystemExit):
            mod.main([])


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_required_pr(self):
        parser = mod.build_parser()
        args = parser.parse_args(["--pr", "42"])
        assert args.pr == 42
        assert args.output_format == "json"

    def test_all_args(self):
        parser = mod.build_parser()
        args = parser.parse_args([
            "--pr", "42", "--owner", "myorg", "--repo", "myrepo", "--format", "markdown",
        ])
        assert args.owner == "myorg"
        assert args.repo == "myrepo"
        assert args.output_format == "markdown"
