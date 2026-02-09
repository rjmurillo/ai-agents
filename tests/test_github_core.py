"""Tests for GitHub Core module, porting and exceeding Pester coverage."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core import (
    RateLimitResult,
    assert_gh_authenticated,
    assert_valid_body_file,
    check_workflow_rate_limit,
    create_issue_comment,
    error_and_exit,
    get_all_prs_with_comments,
    get_bot_authors,
    get_bot_authors_config,
    get_issue_comments,
    get_priority_emoji,
    get_reaction_emoji,
    get_repo_info,
    get_trusted_source_comments,
    get_unresolved_review_threads,
    gh_api_paginated,
    gh_graphql,
    is_gh_authenticated,
    is_github_name_valid,
    is_safe_file_path,
    resolve_repo_params,
    update_issue_comment,
)
from scripts.github_core.api import _403_PATTERN, _DEFAULT_BOTS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    """Build a CompletedProcess for mocking."""
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _mock_run(stdout: str = "", stderr: str = "", rc: int = 0):
    """Return a side_effect function that always returns a fixed CompletedProcess."""

    def _side_effect(*args, **kwargs):
        return _completed(stdout=stdout, stderr=stderr, rc=rc)

    return _side_effect


def _thread(tid: str, resolved: bool, db_id: int) -> dict:
    """Build a minimal review thread dict for GraphQL response mocking."""
    return {
        "id": tid,
        "isResolved": resolved,
        "comments": {"nodes": [{"databaseId": db_id}]},
    }


# ---------------------------------------------------------------------------
# Validation: is_github_name_valid
# ---------------------------------------------------------------------------


class TestIsGitHubNameValid:
    def test_valid_owner(self):
        assert is_github_name_valid("rjmurillo", "Owner") is True

    def test_valid_owner_with_hyphens(self):
        assert is_github_name_valid("my-org", "Owner") is True

    def test_owner_cannot_start_with_hyphen(self):
        assert is_github_name_valid("-badname", "Owner") is False

    def test_owner_cannot_end_with_hyphen(self):
        assert is_github_name_valid("badname-", "Owner") is False

    def test_owner_max_39_chars(self):
        assert is_github_name_valid("a" * 39, "Owner") is True
        # Pattern: start(1) + middle(0-37) + end(1) = max 39 chars
        assert is_github_name_valid("a" * 40, "Owner") is False

    def test_valid_repo(self):
        assert is_github_name_valid("ai-agents", "Repo") is True

    def test_repo_allows_dots(self):
        assert is_github_name_valid("my.repo.name", "Repo") is True

    def test_repo_allows_underscores(self):
        assert is_github_name_valid("my_repo", "Repo") is True

    def test_repo_max_100_chars(self):
        assert is_github_name_valid("a" * 100, "Repo") is True
        assert is_github_name_valid("a" * 101, "Repo") is False

    def test_empty_name_is_invalid(self):
        assert is_github_name_valid("", "Owner") is False
        assert is_github_name_valid("", "Repo") is False

    def test_whitespace_only_is_invalid(self):
        assert is_github_name_valid("   ", "Owner") is False

    def test_invalid_type_returns_false(self):
        assert is_github_name_valid("foo", "Invalid") is False


# ---------------------------------------------------------------------------
# Validation: is_safe_file_path
# ---------------------------------------------------------------------------


class TestIsSafeFilePath:
    def test_safe_path_within_base(self, tmp_path: Path):
        child = tmp_path / "child.txt"
        child.touch()
        assert is_safe_file_path(str(child), str(tmp_path)) is True

    def test_traversal_blocked(self, tmp_path: Path):
        bad_path = str(tmp_path / ".." / "escape.txt")
        assert is_safe_file_path(bad_path, str(tmp_path)) is False

    def test_default_base_is_cwd(self, tmp_path: Path):
        child = tmp_path / "file.txt"
        child.touch()
        with patch("os.getcwd", return_value=str(tmp_path)):
            assert is_safe_file_path(str(child)) is True

    def test_rejects_backslash_traversal(self):
        assert is_safe_file_path("foo\\..\\bar") is False


# ---------------------------------------------------------------------------
# Validation: assert_valid_body_file
# ---------------------------------------------------------------------------


class TestAssertValidBodyFile:
    def test_raises_when_file_missing(self):
        with pytest.raises(SystemExit) as exc:
            assert_valid_body_file("/nonexistent/path/file.txt")
        assert exc.value.code == 2

    def test_passes_when_file_exists(self, tmp_path: Path):
        f = tmp_path / "body.md"
        f.write_text("hello")
        assert_valid_body_file(str(f))

    def test_raises_on_traversal(self, tmp_path: Path):
        # Create file at parent so it exists, but path has traversal
        parent = tmp_path.parent
        f = parent / "body.md"
        f.write_text("hello")
        try:
            traversal_path = str(tmp_path / ".." / "body.md")
            with pytest.raises(SystemExit) as exc:
                assert_valid_body_file(traversal_path, str(tmp_path))
            assert exc.value.code == 1
        finally:
            f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorAndExit:
    def test_raises_system_exit_with_code(self):
        with pytest.raises(SystemExit) as exc:
            error_and_exit("boom", 3)
        assert exc.value.code == 3

    def test_writes_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            error_and_exit("error message", 1)
        assert "error message" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestGetRepoInfo:
    def test_parses_https_remote(self):
        stdout = "https://github.com/rjmurillo/ai-agents.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == {"Owner": "rjmurillo", "Repo": "ai-agents"}

    def test_parses_ssh_remote(self):
        stdout = "git@github.com:myorg/myrepo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info == {"Owner": "myorg", "Repo": "myrepo"}

    def test_returns_none_when_not_git_repo(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="fatal")):
            assert get_repo_info() is None

    def test_returns_none_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)):
            assert get_repo_info() is None

    def test_strips_dot_git_suffix(self):
        stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=_completed(stdout=stdout)):
            info = get_repo_info()
        assert info is not None
        assert info["Repo"] == "repo"


class TestResolveRepoParams:
    def test_uses_provided_params(self):
        result = resolve_repo_params("myowner", "myrepo")
        assert result == {"Owner": "myowner", "Repo": "myrepo"}

    def test_infers_from_git_remote(self):
        with patch(
            "scripts.github_core.api.get_repo_info",
            return_value={"Owner": "inferred", "Repo": "repo"},
        ):
            result = resolve_repo_params()
        assert result == {"Owner": "inferred", "Repo": "repo"}

    def test_exits_when_cannot_infer(self):
        with patch("scripts.github_core.api.get_repo_info", return_value=None):
            with pytest.raises(SystemExit) as exc:
                resolve_repo_params()
            assert exc.value.code == 1

    def test_exits_on_invalid_owner(self):
        with pytest.raises(SystemExit) as exc:
            resolve_repo_params("-bad", "repo")
        assert exc.value.code == 1

    def test_exits_on_invalid_repo(self):
        with pytest.raises(SystemExit) as exc:
            resolve_repo_params("owner", "bad/repo/name!")
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestIsGhAuthenticated:
    def test_true_when_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert is_gh_authenticated() is True

    def test_false_when_not_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            assert is_gh_authenticated() is False

    def test_false_when_gh_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert is_gh_authenticated() is False

    def test_returns_bool(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert isinstance(is_gh_authenticated(), bool)


class TestAssertGhAuthenticated:
    def test_passes_when_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert_gh_authenticated()

    def test_exits_4_when_not_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
            assert exc.value.code == 4


# ---------------------------------------------------------------------------
# API: gh_api_paginated
# ---------------------------------------------------------------------------


class TestGhApiPaginated:
    def test_single_page(self):
        items = [{"id": 1}, {"id": 2}]
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(items))):
            result = gh_api_paginated("repos/o/r/issues")
        assert result == items

    def test_multi_page(self):
        page1 = [{"id": i} for i in range(100)]
        page2 = [{"id": 100}]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            data = page1 if call_count == 1 else page2
            return _completed(stdout=json.dumps(data))

        with patch("subprocess.run", side_effect=_side_effect):
            result = gh_api_paginated("repos/o/r/issues", page_size=100)
        assert len(result) == 101

    def test_empty_response(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")):
            result = gh_api_paginated("repos/o/r/issues")
        assert result == []

    def test_first_page_failure_exits(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="error")):
            with pytest.raises(SystemExit) as exc:
                gh_api_paginated("repos/o/r/issues")
            assert exc.value.code == 3

    def test_mid_pagination_failure_returns_partial(self):
        page1 = [{"id": i} for i in range(100)]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=json.dumps(page1))
            return _completed(rc=1, stderr="rate limited")

        with patch("subprocess.run", side_effect=_side_effect):
            with pytest.warns(UserWarning, match="Returning partial results"):
                result = gh_api_paginated("repos/o/r/issues")
        assert len(result) == 100

    def test_endpoint_with_query_params_uses_ampersand(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")) as mock:
            gh_api_paginated("repos/o/r/issues?state=open")
        call_args = mock.call_args[0][0]
        assert "&per_page=" in call_args[2]


# ---------------------------------------------------------------------------
# API: gh_graphql
# ---------------------------------------------------------------------------


class TestGhGraphQL:
    def test_simple_query(self):
        response = json.dumps({"data": {"viewer": {"login": "testuser"}}})
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            result = gh_graphql("query { viewer { login } }")
        assert result == {"viewer": {"login": "testuser"}}

    def test_with_string_variables(self):
        response = json.dumps({"data": {"repository": {"name": "ai-agents"}}})
        with patch("subprocess.run", return_value=_completed(stdout=response)) as mock:
            gh_graphql("query($owner: String!) { ... }", {"owner": "rjmurillo"})
        cmd = mock.call_args[0][0]
        assert "-f" in cmd
        assert "owner=rjmurillo" in cmd

    def test_with_int_variables(self):
        response = json.dumps({"data": {}})
        with patch("subprocess.run", return_value=_completed(stdout=response)) as mock:
            gh_graphql("query($num: Int!) { ... }", {"num": 42})
        cmd = mock.call_args[0][0]
        assert "-F" in cmd
        assert "num=42" in cmd

    def test_transport_error_raises(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="network error")):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                gh_graphql("query { viewer { login } }")

    def test_graphql_level_error_raises(self):
        response = json.dumps({"data": None, "errors": [{"message": "Not found"}]})
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            with pytest.raises(RuntimeError, match="GraphQL errors.*Not found"):
                gh_graphql("query { ... }")

    def test_invalid_json_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="Failed to parse"):
                gh_graphql("query { ... }")


# ---------------------------------------------------------------------------
# API: get_all_prs_with_comments
# ---------------------------------------------------------------------------


class TestGetAllPRsWithComments:
    def _make_pr(self, number: int, updated: str, has_comments: bool = True):
        threads = []
        if has_comments:
            threads = [
                {
                    "isResolved": False,
                    "isOutdated": False,
                    "comments": {
                        "nodes": [
                            {
                                "id": "c1",
                                "body": "fix this",
                                "author": {"login": "reviewer"},
                                "createdAt": updated,
                                "path": "file.py",
                            }
                        ]
                    },
                }
            ]
        return {
            "number": number,
            "title": f"PR #{number}",
            "state": "OPEN",
            "author": {"login": "author"},
            "createdAt": updated,
            "updatedAt": updated,
            "mergedAt": None,
            "closedAt": None,
            "reviewThreads": {"nodes": threads},
        }

    def test_returns_prs_with_comments(self):
        pr = self._make_pr(1, "2026-01-15T00:00:00Z")
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [pr],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments(
                "owner", "repo", datetime(2026, 1, 1, tzinfo=UTC)
            )
        assert len(result) == 1
        assert result[0]["number"] == 1

    def test_excludes_prs_without_comments(self):
        pr_with = self._make_pr(1, "2026-01-15T00:00:00Z", has_comments=True)
        pr_without = self._make_pr(2, "2026-01-15T00:00:00Z", has_comments=False)
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [pr_with, pr_without],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments(
                "owner", "repo", datetime(2026, 1, 1, tzinfo=UTC)
            )
        assert len(result) == 1

    def test_stops_when_pr_older_than_since(self):
        old_pr = self._make_pr(1, "2025-01-01T00:00:00Z")
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                        "nodes": [old_pr],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments(
                "owner", "repo", datetime(2026, 1, 1, tzinfo=UTC)
            )
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Issue comments
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 403 Pattern matching (ported from Pester behavioral tests)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Trusted sources
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------


class TestGetBotAuthorsConfig:
    def test_returns_dict_with_required_keys(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text(
            "reviewer:\n  - bot1\nautomation:\n  - bot2\nrepository:\n  - bot3\n"
        )
        # Mock _find_repo_root to skip CWE-22 check (tmp_path is outside repo)
        with patch("scripts.github_core.api._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert set(result.keys()) == {"reviewer", "automation", "repository"}

    def test_each_category_has_entries(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text(
            "reviewer:\n  - r1\n  - r2\nautomation:\n  - a1\nrepository:\n  - p1\n"
        )
        with patch("scripts.github_core.api._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert len(result["reviewer"]) == 2
        assert len(result["automation"]) == 1
        assert len(result["repository"]) == 1

    def test_caches_result(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("reviewer:\n  - bot1\nautomation:\n  - bot2\nrepository:\n  - bot3\n")
        with patch("scripts.github_core.api._find_repo_root", return_value=None):
            r1 = get_bot_authors_config(config_path=str(config), force=True)
            r2 = get_bot_authors_config(config_path=str(config))
        assert r1 is r2

    def test_force_reloads(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("reviewer:\n  - old\nautomation:\n  - a\nrepository:\n  - r\n")
        with patch("scripts.github_core.api._find_repo_root", return_value=None):
            get_bot_authors_config(config_path=str(config), force=True)
            config.write_text("reviewer:\n  - new\nautomation:\n  - a\nrepository:\n  - r\n")
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert "new" in result["reviewer"]

    def test_falls_back_to_defaults_when_missing(self):
        result = get_bot_authors_config(config_path="/nonexistent/config.yml", force=True)
        assert "coderabbitai[bot]" in result["reviewer"]

    def test_falls_back_on_empty_config(self, tmp_path: Path):
        config = tmp_path / "bot-authors.yml"
        config.write_text("")
        with patch("scripts.github_core.api._find_repo_root", return_value=None):
            result = get_bot_authors_config(config_path=str(config), force=True)
        assert result == _DEFAULT_BOTS

    def test_path_traversal_uses_defaults(self, tmp_path: Path):
        # Create a file that resolves outside the "repo root"
        outside = tmp_path / "outside.yml"
        outside.write_text("reviewer:\n  - evil\n")
        # Set repo root to a subdirectory so the file is outside it
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        with patch(
            "scripts.github_core.api._find_repo_root",
            return_value=str(repo_root),
        ):
            with pytest.warns(UserWarning, match="outside repository root"):
                result = get_bot_authors_config(config_path=str(outside), force=True)
        assert result == _DEFAULT_BOTS


class TestGetBotAuthors:
    def test_all_returns_combined_sorted(self):
        with patch(
            "scripts.github_core.api.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("all")
        assert "coderabbitai[bot]" in result
        assert "github-actions[bot]" in result
        assert "rjmurillo-bot" in result
        assert result == sorted(result)

    def test_reviewer_category(self):
        with patch(
            "scripts.github_core.api.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("reviewer")
        assert "coderabbitai[bot]" in result
        assert "github-copilot[bot]" in result
        assert "github-actions[bot]" not in result
        assert "rjmurillo-bot" not in result

    def test_automation_category(self):
        with patch(
            "scripts.github_core.api.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("automation")
        assert "github-actions[bot]" in result
        assert "dependabot[bot]" in result
        assert "coderabbitai[bot]" not in result

    def test_repository_category(self):
        with patch(
            "scripts.github_core.api.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors("repository")
        assert "rjmurillo-bot" in result
        assert "copilot-swe-agent[bot]" in result
        assert "github-actions[bot]" not in result

    def test_default_is_all(self):
        with patch(
            "scripts.github_core.api.get_bot_authors_config",
            return_value=_DEFAULT_BOTS,
        ):
            result = get_bot_authors()
        assert len(result) == len(set(b for v in _DEFAULT_BOTS.values() for b in v))


# ---------------------------------------------------------------------------
# PR review threads
# ---------------------------------------------------------------------------


class TestGetUnresolvedReviewThreads:
    def test_returns_unresolved_threads(self):
        graphql_response = json.dumps({
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                _thread("t1", False, 1),
                                _thread("t2", True, 2),
                                _thread("t3", False, 3),
                            ]
                        }
                    }
                }
            }
        })
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert len(result) == 2
        assert all(not t["isResolved"] for t in result)

    def test_returns_empty_on_all_resolved(self):
        graphql_response = json.dumps({
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                _thread("t1", True, 1),
                            ]
                        }
                    }
                }
            }
        })
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_returns_empty_on_no_threads(self):
        graphql_response = json.dumps({
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": []
                        }
                    }
                }
            }
        })
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_returns_empty_on_api_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="network error")):
            with pytest.warns(UserWarning, match="Failed to query review threads"):
                result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_never_returns_none(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="fail")):
            with pytest.warns(UserWarning):
                result = get_unresolved_review_threads("owner", "repo", 1)
        assert result is not None
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------

RATE_LIMIT_ALL_OK = json.dumps({
    "resources": {
        "core": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
        "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
        "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
    }
})

RATE_LIMIT_CORE_LOW = json.dumps({
    "resources": {
        "core": {"remaining": 50, "limit": 5000, "reset": 1234567890},
        "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
        "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
        "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
    }
})

RATE_LIMIT_MISSING_RESOURCE = json.dumps({
    "resources": {
        "core": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
        "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
    }
})


class TestCheckWorkflowRateLimit:
    def test_success_all_above_threshold(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert result.success is True
        assert result.core_remaining == 5000

    def test_failure_core_below_threshold(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit()
        assert result.success is False
        assert result.resources["core"]["Passed"] is False

    def test_custom_thresholds_pass(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 10})
        assert result.success is True

    def test_custom_thresholds_fail(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 100})
        assert result.success is False

    def test_markdown_summary(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert "API Rate Limit Status" in result.summary_markdown
        assert "| Resource |" in result.summary_markdown
        assert "OK" in result.summary_markdown

    def test_missing_resource_warns(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_MISSING_RESOURCE)):
            with pytest.warns(UserWarning, match="code_search"):
                result = check_workflow_rate_limit()
        assert result.success is False

    def test_raises_on_api_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="API error")):
            with pytest.raises(RuntimeError, match="Failed to fetch rate limits"):
                check_workflow_rate_limit()

    def test_returns_rate_limit_result_type(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert isinstance(result, RateLimitResult)


# ---------------------------------------------------------------------------
# Formatting: Priority emoji
# ---------------------------------------------------------------------------


class TestGetPriorityEmoji:
    def test_p0_fire(self):
        assert get_priority_emoji("P0") == "\U0001f525"

    def test_p1_exclamation(self):
        assert get_priority_emoji("P1") == "\u2757"

    def test_p2_dash(self):
        assert get_priority_emoji("P2") == "\u2796"

    def test_p3_down_arrow(self):
        assert get_priority_emoji("P3") == "\u2b07\ufe0f"

    def test_unknown_question_mark(self):
        assert get_priority_emoji("unknown") == "\u2754"


# ---------------------------------------------------------------------------
# Formatting: Reaction emoji
# ---------------------------------------------------------------------------


class TestGetReactionEmoji:
    def test_thumbs_up(self):
        assert get_reaction_emoji("+1") == "\U0001f44d"

    def test_thumbs_down(self):
        assert get_reaction_emoji("-1") == "\U0001f44e"

    def test_laugh(self):
        assert get_reaction_emoji("laugh") == "\U0001f604"

    def test_confused(self):
        assert get_reaction_emoji("confused") == "\U0001f615"

    def test_heart(self):
        assert get_reaction_emoji("heart") == "\u2764\ufe0f"

    def test_hooray(self):
        assert get_reaction_emoji("hooray") == "\U0001f389"

    def test_rocket(self):
        assert get_reaction_emoji("rocket") == "\U0001f680"

    def test_eyes(self):
        assert get_reaction_emoji("eyes") == "\U0001f440"

    def test_unknown_returns_input(self):
        assert get_reaction_emoji("custom") == "custom"
