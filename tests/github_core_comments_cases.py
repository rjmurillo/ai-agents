"""Focused GitHub Core contract cases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core import (
    create_issue_comment,
    get_bot_authors,
    get_bot_authors_config,
    get_issue_comments,
    get_trusted_source_comments,
    safe_log_str,
    update_issue_comment,
)
from scripts.github_core.api import _403_PATTERN
from scripts.github_core.bot_config import _DEFAULT_BOTS
from tests.github_core_test_helpers import _completed


class TestGetIssueComments:
    def test_delegates_to_paginated(self):
        comments = [{"id": 1, "body": "hello"}]
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(comments))):
            result = get_issue_comments("owner", "repo", 42)
        assert result == comments


class TestUpdateIssueComment:
    def test_success(self):
        response = {"id": 123, "body": "updated"}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(response))):
            result = update_issue_comment("owner", "repo", 123, "updated")
        assert result["body"] == "updated"

    def test_403_exits_code_4(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="HTTP 403: Forbidden"),
        ):
            with pytest.raises(SystemExit) as exc:
                update_issue_comment("owner", "repo", 123, "text")
            assert exc.value.code == 4

    def test_generic_api_error_exits_code_3(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="HTTP 500: Internal Server Error"),
        ):
            with pytest.raises(SystemExit) as exc:
                update_issue_comment("owner", "repo", 123, "text")
            assert exc.value.code == 3

    def test_sends_payload_via_stdin(self):
        response = {"id": 1, "body": "test"}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(response))) as mock:
            update_issue_comment("owner", "repo", 1, "test body")
        assert mock.call_args.kwargs.get("input") == json.dumps({"body": "test body"})

    def test_invalid_json_response_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="not valid JSON"):
                update_issue_comment("owner", "repo", 123, "text")


class TestCreateIssueComment:
    def test_success(self):
        response = {"id": 999, "body": "new comment"}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(response))):
            result = create_issue_comment("owner", "repo", 42, "new comment")
        assert result["body"] == "new comment"

    def test_api_failure_exits_3(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(SystemExit) as exc:
                create_issue_comment("owner", "repo", 42, "text")
            assert exc.value.code == 3

    def test_invalid_json_response_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="not valid JSON"):
                create_issue_comment("owner", "repo", 42, "text")


class Test403PatternMatching:
    @pytest.mark.parametrize(
        "error_msg",
        [
            "HTTP 403: Forbidden",
            "status: 403",
            "gh: Resource not accessible by integration (HTTP 403)",
            "403 Forbidden",
            "FORBIDDEN",
            "Forbidden",
            "Error code: 403",
        ],
    )
    def test_detects_403_errors(self, error_msg: str):
        assert _403_PATTERN.search(error_msg) is not None

    @pytest.mark.parametrize(
        "error_msg",
        [
            "HTTP 401: Not authenticated",
            "HTTP 500: Internal Server Error",
            "Connection refused",
            "Comment ID 4030 not found",
            "Reference 1403245 is invalid",
        ],
    )
    def test_rejects_non_403_errors(self, error_msg: str):
        assert _403_PATTERN.search(error_msg) is None


class TestGetTrustedSourceComments:
    def test_filters_to_trusted_users(self):
        comments = [
            {"id": 1, "user": {"login": "alice"}},
            {"id": 2, "user": {"login": "bob"}},
            {"id": 3, "user": {"login": "alice"}},
        ]
        result = get_trusted_source_comments(comments, ["alice"])
        assert len(result) == 2
        assert all(c["user"]["login"] == "alice" for c in result)

    def test_empty_comments_returns_empty(self):
        assert get_trusted_source_comments([], ["alice"]) == []

    def test_no_matches_returns_empty(self):
        comments = [{"id": 1, "user": {"login": "eve"}}]
        assert get_trusted_source_comments(comments, ["alice"]) == []


class TestGetBotAuthorsConfig:
    def test_returns_dict_with_required_keys(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text(
            "reviewer:\n  - bot1\nautomation:\n  - bot2\nrepository:\n  - bot3\n", encoding="utf-8"
        )
        # Mock _find_repo_root to skip CWE-22 check (tmp_path is outside repo)
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert set(result.keys()) == {"reviewer", "automation", "repository"}

    def test_each_category_has_entries(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text(
            "reviewer:\n  - r1\n  - r2\nautomation:\n  - a1\nrepository:\n  - p1\n",
            encoding="utf-8",
        )
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert len(result["reviewer"]) == 2
        assert len(result["automation"]) == 1
        assert len(result["repository"]) == 1

    def test_caches_result(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text(
            "reviewer:\n  - bot1\nautomation:\n  - bot2\nrepository:\n  - bot3\n", encoding="utf-8"
        )
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            r1 = get_bot_authors_config(config_path=str(config), force=True)
            r2 = get_bot_authors_config(config_path=str(config))
        assert r1 is r2

    def test_force_reloads(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text(
            "reviewer:\n  - old\nautomation:\n  - a\nrepository:\n  - r\n", encoding="utf-8"
        )
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            get_bot_authors_config(config_path=str(config), force=True)
            config.write_text(
                "reviewer:\n  - new\nautomation:\n  - a\nrepository:\n  - r\n", encoding="utf-8"
            )
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert "new" in result["reviewer"]

    def test_falls_back_to_defaults_when_missing(self):
        result = get_bot_authors_config(config_path="/nonexistent/config.yml", force=True)
        assert "coderabbitai[bot]" in result["reviewer"]

    def test_falls_back_on_empty_config(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("", encoding="utf-8")
        with patch("scripts.github_core.bot_config._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert result == _DEFAULT_BOTS

    def test_path_traversal_uses_defaults(self, tmp_path: Path):
        # Create a file that resolves outside the "repo root"
        outside = tmp_path / "outside.yml"
        outside.write_text("reviewer:\n  - evil\n", encoding="utf-8")
        # Set repo root to a subdirectory so the file is outside it
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        with patch(
            "scripts.github_core.bot_config._find_repo_root",
            return_value=str(repo_root),
        ):
            with pytest.warns(UserWarning, match="outside repository root"):
                result = get_bot_authors_config(config_path=str(outside), force=True)
        assert result == _DEFAULT_BOTS


class TestGetBotAuthors:
    def test_all_returns_combined_sorted(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("all")
        assert "coderabbitai[bot]" in result
        assert "github-actions[bot]" in result
        assert "rjmurillo-bot" in result
        assert result == sorted(result)

    def test_reviewer_category(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("reviewer")
        assert "coderabbitai[bot]" in result
        assert "github-copilot[bot]" in result
        assert "github-actions[bot]" not in result
        assert "rjmurillo-bot" not in result

    def test_automation_category(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("automation")
        assert "github-actions[bot]" in result
        assert "dependabot[bot]" in result
        assert "coderabbitai[bot]" not in result

    def test_repository_category(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("repository")
        assert "rjmurillo-bot" in result
        assert "copilot-swe-agent[bot]" in result
        assert "github-actions[bot]" not in result

    def test_default_is_all(self):
        with patch(
            "scripts.github_core.bot_config.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors()
        assert len(result) == len(set(b for v in _DEFAULT_BOTS.values() for b in v))


class TestSafeLogStr:
    def test_strips_carriage_return(self):
        assert safe_log_str("a\rb") == "a\\rb"

    def test_strips_newline(self):
        assert safe_log_str("a\nb") == "a\\nb"

    def test_strips_crlf_log_forging_attempt(self):
        """Defense against CWE-117: an attacker-controlled error message
        embedding `\\r\\n op=review_threads_failed reason=fake` must not
        produce a forged log line.
        """
        forged = "real_error\r\n op=review_threads_failed reason=fake"
        sanitized = safe_log_str(forged)
        assert "\r" not in sanitized
        assert "\n" not in sanitized
        assert sanitized.startswith("real_error\\r\\n")

    def test_handles_non_string(self):
        assert safe_log_str(42) == "42"
        assert safe_log_str(RuntimeError("oops")) == "oops"
