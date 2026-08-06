"""Tests for get_pr_comments_by_reviewer.py skill script."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)
_SCRIPT = _SCRIPTS_DIR / "get_pr_comments_by_reviewer.py"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_pr_comments_by_reviewer")
main = _mod.main
build_parser = _mod.build_parser
get_pr_comments_by_reviewer = _mod.get_pr_comments_by_reviewer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE = "get_pr_comments_by_reviewer"


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _author_response(login: object = "author1", actor_id: int | None = None) -> dict:
    return {
        "repository": {
            "pullRequest": {
                "author": {
                    "login": login,
                    "databaseId": actor_id,
                }
            }
        }
    }


def _make_review_comment(
    login: str = "reviewer1",
    body: str = "Fix this",
    created_at: str = "2025-06-01T00:00:00Z",
    path: str = "src/main.py",
    user_type: str = "User",
    actor_id: int | None = None,
):
    return {
        "user": {"login": login, "type": user_type, "id": actor_id},
        "body": body,
        "created_at": created_at,
        "updated_at": created_at,
        "path": path,
        "html_url": "https://github.com/o/r/pull/1#comment",
    }


def _make_issue_comment(
    login: str = "reviewer1",
    body: str = "Looks good",
    created_at: str = "2025-06-01T00:00:00Z",
    user_type: str = "User",
    actor_id: int | None = None,
):
    return {
        "user": {"login": login, "type": user_type, "id": actor_id},
        "body": body,
        "created_at": created_at,
        "updated_at": created_at,
        "html_url": "https://github.com/o/r/pull/1#issuecomment",
    }


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_single_pr(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == [42]

    def test_multiple_prs(self):
        args = build_parser().parse_args(["--pull-request", "1", "2", "3"])
        assert args.pull_request == [1, 2, 3]

    def test_include_reviewer(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--include-reviewer", "alice", "bob"]
        )
        assert args.include_reviewer == ["alice", "bob"]

    def test_exclude_reviewer(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--exclude-reviewer", "bot1"]
        )
        assert args.exclude_reviewer == ["bot1"]

    def test_comment_type_default(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.comment_type == "all"

    def test_comment_type_review_only(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--comment-type", "review"]
        )
        assert args.comment_type == "review"

    def test_include_self_comments_default_false(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.include_self_comments is False

    def test_since_until(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--since", "2025-01-01", "--until", "2025-06-30"]
        )
        assert args.since == "2025-01-01"
        assert args.until == "2025-06-30"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_foreign_github_workspace_uses_bundled_library(self):
        env = os.environ.copy()
        env.pop("COPILOT_PLUGIN_ROOT", None)
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env["GITHUB_WORKSPACE"] = str(Path(__file__).resolve().parent / "foreign-workspace")

        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            env=env,
            cwd=Path(__file__).resolve().parents[1],
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert "grouped by reviewer" in result.stdout

    def test_not_authenticated_exits_4(self):
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    @pytest.mark.parametrize("failing_endpoint", ["pulls", "issues"])
    def test_partial_pagination_exits_3(
        self,
        failing_endpoint: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        author_response = _author_response()

        def rest(endpoint: str, **_kwargs) -> list[dict]:
            if f"/{failing_endpoint}/" in endpoint:
                warnings.warn(
                    "GitHub API page 2 failed. Returning partial results.",
                    UserWarning,
                    stacklevel=2,
                )
                return [_make_review_comment()]
            return []

        with patch(
            f"{_MODULE}.assert_gh_authenticated",
        ), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            f"{_MODULE}.gh_graphql",
            return_value=author_response,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            side_effect=rest,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "42"])

        assert exc.value.code == 3
        assert '"success": true' not in capsys.readouterr().out.lower()

    @pytest.mark.parametrize("location", ["author", "comment"])
    def test_non_string_actor_login_exits_3(
        self,
        location: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        author_login: str | int = 42 if location == "author" else "author1"
        author_response = _author_response(author_login)
        comments = (
            [{"user": {"login": 42, "type": "Bot"}, "body": "bad"}]
            if location == "comment"
            else []
        )
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
        ), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            f"{_MODULE}.gh_graphql",
            return_value=author_response,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            return_value=comments,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "42", "--comment-type", "review"])

        assert exc.value.code == 3
        assert '"success": true' not in capsys.readouterr().out.lower()

    def test_no_comments(self, capsys):
        author_response = _author_response()
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
        ), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            f"{_MODULE}.gh_graphql",
            return_value=author_response,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            return_value=[],
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["total_comments"] == 0
        assert output["total_reviewers"] == 0

    def test_groups_by_reviewer(self, capsys):
        author_response = _author_response()
        review_comments = [
            _make_review_comment("alice", "Fix bug"),
            _make_review_comment("bob", "Add test"),
            _make_review_comment("alice", "Check style"),
        ]
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
        ), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            f"{_MODULE}.gh_graphql",
            return_value=author_response,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            return_value=review_comments,
        ):
            rc = main(["--pull-request", "1", "--comment-type", "review"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["total_reviewers"] == 2
        assert output["total_comments"] == 3
        # Sorted by count descending: alice(2), bob(1)
        assert output["reviewers"][0]["login"] == "alice"
        assert output["reviewers"][0]["total_comments"] == 2
        assert output["reviewers"][1]["login"] == "bob"
        assert output["reviewers"][1]["total_comments"] == 1


# ---------------------------------------------------------------------------
# Tests: get_pr_comments_by_reviewer (unit)
# ---------------------------------------------------------------------------


class TestGetPrCommentsByReviewer:
    def _run(
        self,
        review_comments=None,
        issue_comments=None,
        pr_author="author1",
        pr_author_id: int | None = None,
        **kwargs,
    ):
        review_comments = review_comments or []
        issue_comments = issue_comments or []
        author_response = _author_response(pr_author, pr_author_id)

        def paginated_side_effect(endpoint, **_kw):
            if "/pulls/" in endpoint and "/comments" in endpoint:
                return review_comments
            if "/issues/" in endpoint and "/comments" in endpoint:
                return issue_comments
            return []

        with patch(
            f"{_MODULE}.gh_graphql",
            return_value=author_response,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            side_effect=paginated_side_effect,
        ):
            return get_pr_comments_by_reviewer("o", "r", [1], **kwargs)

    def test_excludes_self_comments(self):
        result = self._run(
            review_comments=[_make_review_comment("author1", "Self comment")],
            pr_author="author1",
        )
        assert result["total_comments"] == 0
        assert result["total_reviewers"] == 0

    def test_includes_self_comments_when_flag_set(self):
        result = self._run(
            review_comments=[_make_review_comment("author1", "Self comment")],
            pr_author="author1",
            exclude_self_comments=False,
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "author1"

    def test_include_reviewer_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice"),
                _make_review_comment("bob"),
            ],
            include_reviewers=["alice"],
        )
        assert result["total_reviewers"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_exclude_reviewer_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice"),
                _make_review_comment("bob"),
            ],
            exclude_reviewers=["bob"],
        )
        assert result["total_reviewers"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_since_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice", created_at="2025-01-01T00:00:00Z"),
                _make_review_comment("bob", created_at="2025-07-01T00:00:00Z"),
            ],
            since="2025-06-01T00:00:00Z",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "bob"

    def test_until_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice", created_at="2025-01-01T00:00:00Z"),
                _make_review_comment("bob", created_at="2025-07-01T00:00:00Z"),
            ],
            until="2025-06-01T00:00:00Z",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_review_comment_type_only(self):
        result = self._run(
            review_comments=[_make_review_comment("alice")],
            issue_comments=[_make_issue_comment("bob")],
            comment_type="review",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_issue_comment_type_only(self):
        result = self._run(
            review_comments=[_make_review_comment("alice")],
            issue_comments=[_make_issue_comment("bob")],
            comment_type="issue",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "bob"

    def test_all_comment_types(self):
        result = self._run(
            review_comments=[_make_review_comment("alice")],
            issue_comments=[_make_issue_comment("alice")],
            comment_type="all",
        )
        assert result["total_comments"] == 2
        assert result["reviewers"][0]["login"] == "alice"
        assert result["reviewers"][0]["review_comments"] == 1
        assert result["reviewers"][0]["issue_comments"] == 1

    def test_tracks_prs_per_reviewer(self):
        author_response = _author_response()
        review_comments_pr1 = [_make_review_comment("alice")]
        review_comments_pr2 = [_make_review_comment("alice")]

        call_count = 0

        def paginated_side_effect(endpoint, **_kw):
            nonlocal call_count
            if "/pulls/" in endpoint and "/comments" in endpoint:
                call_count += 1
                if call_count == 1:
                    return review_comments_pr1
                return review_comments_pr2
            return []

        with patch(
            f"{_MODULE}.gh_graphql",
            return_value=author_response,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            side_effect=paginated_side_effect,
        ):
            result = get_pr_comments_by_reviewer("o", "r", [1, 2])

        assert result["prs_processed"] == 2
        assert result["reviewers"][0]["login"] == "alice"
        assert result["reviewers"][0]["total_comments"] == 2
        assert len(result["reviewers"][0]["prs"]) == 2

    def test_empty_login_skipped(self):
        result = self._run(
            review_comments=[_make_review_comment("")],
        )
        assert result["total_comments"] == 0

    def test_sorted_by_comment_count(self):
        result = self._run(
            review_comments=[
                _make_review_comment("bob"),
                _make_review_comment("alice"),
                _make_review_comment("alice"),
                _make_review_comment("alice"),
            ],
        )
        assert result["reviewers"][0]["login"] == "alice"
        assert result["reviewers"][0]["total_comments"] == 3
        assert result["reviewers"][1]["login"] == "bob"
        assert result["reviewers"][1]["total_comments"] == 1

    # -----------------------------------------------------------------------
    # Bot alias canonicalization (issue #4378)
    # -----------------------------------------------------------------------

    def test_copilot_aliases_group_as_one_reviewer(self):
        result = self._run(
            review_comments=[
                _make_review_comment("Copilot", user_type="Bot"),
                _make_review_comment("copilot-pull-request-reviewer[bot]", user_type="Bot"),
            ],
            issue_comments=[_make_issue_comment("copilot-pull-request-reviewer", user_type="Bot")],
        )
        assert result["total_reviewers"] == 1
        entry = result["reviewers"][0]
        assert entry["login"] == "github-copilot[bot]"
        assert entry["total_comments"] == 3
        assert entry["actor_ids"] == []
        assert sorted(entry["aliases"]) == [
            "Copilot",
            "copilot-pull-request-reviewer",
            "copilot-pull-request-reviewer[bot]",
        ]

    def test_the_coding_agent_stays_separate_from_the_code_reviewer(self):
        """Two accounts (issue #4378): merging them hides the review."""
        result = self._run(
            review_comments=[
                _make_review_comment("copilot-pull-request-reviewer[bot]", user_type="Bot"),
                _make_review_comment("copilot-swe-agent[bot]", user_type="Bot"),
            ],
        )
        assert sorted(r["login"] for r in result["reviewers"]) == [
            "copilot-swe-agent[bot]",
            "github-copilot[bot]",
        ]

    def test_shared_copilot_login_is_separated_by_account_id(self):
        result = self._run(
            review_comments=[
                _make_review_comment("Copilot", user_type="Bot", actor_id=175728472),
                _make_review_comment("Copilot", user_type="Bot", actor_id=198982749),
            ],
        )
        reviewers = {r["login"]: r for r in result["reviewers"]}
        assert set(reviewers) == {
            "github-copilot[bot]",
            "copilot-swe-agent[bot]",
        }
        assert reviewers["github-copilot[bot]"]["actor_ids"] == [175728472]
        assert reviewers["copilot-swe-agent[bot]"]["actor_ids"] == [198982749]

    def test_shared_account_id_merges_different_aliases(self):
        result = self._run(
            review_comments=[
                _make_review_comment(
                    "coderabbitai[bot]",
                    user_type="Bot",
                    actor_id=136622811,
                ),
                _make_review_comment(
                    "coderabbitai",
                    user_type="Bot",
                    actor_id=136622811,
                ),
            ],
        )
        assert result["total_reviewers"] == 1
        assert sorted(result["reviewers"][0]["aliases"]) == [
            "coderabbitai",
            "coderabbitai[bot]",
        ]

    def test_shared_login_keeps_distinct_ids_separate(self):
        result = self._run(
            review_comments=[
                _make_review_comment("shared-service", actor_id=101),
                _make_review_comment("shared-service", actor_id=202),
            ],
        )
        assert result["total_reviewers"] == 2
        assert {tuple(entry["actor_ids"]) for entry in result["reviewers"]} == {
            (101,),
            (202,),
        }

    def test_distinct_humans_stay_separate(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice"),
                _make_review_comment("bob"),
            ],
        )
        assert result["total_reviewers"] == 2
        for entry in result["reviewers"]:
            assert entry["aliases"] == [entry["login"]]

    def test_include_filter_accepts_any_alias(self):
        result = self._run(
            review_comments=[
                _make_review_comment("copilot-pull-request-reviewer[bot]", user_type="Bot"),
                _make_review_comment("alice"),
            ],
            include_reviewers=["Copilot"],
        )
        assert result["total_reviewers"] == 1
        assert result["reviewers"][0]["login"] == "github-copilot[bot]"

    def test_exclude_filter_removes_every_alias(self):
        result = self._run(
            review_comments=[
                _make_review_comment("Copilot", user_type="Bot"),
                _make_review_comment("copilot-pull-request-reviewer[bot]", user_type="Bot"),
                _make_review_comment("alice"),
            ],
            exclude_reviewers=["copilot-pull-request-reviewer"],
        )
        assert [r["login"] for r in result["reviewers"]] == ["alice"]

    def test_self_comments_match_an_aliased_author(self):
        """gh reports the author as app/..., its own comments as ...[bot]."""
        result = self._run(
            review_comments=[_make_review_comment("copilot-swe-agent[bot]", user_type="Bot")],
            pr_author="app/copilot-swe-agent",
        )
        assert result["total_comments"] == 0

    def test_a_review_of_a_coding_agent_pr_is_not_read_as_a_self_comment(self):
        """The failure the merged map produced: the review vanished."""
        result = self._run(
            review_comments=[
                _make_review_comment("copilot-pull-request-reviewer[bot]", user_type="Bot")
            ],
            pr_author="app/copilot-swe-agent",
        )
        assert result["total_comments"] == 1
        assert [r["login"] for r in result["reviewers"]] == ["github-copilot[bot]"]

    def test_ids_separate_an_ambiguous_author_from_the_reviewer(self):
        result = self._run(
            review_comments=[
                _make_review_comment(
                    "Copilot", user_type="Bot", actor_id=175728472
                )
            ],
            pr_author="Copilot",
            pr_author_id=198982749,
        )
        assert result["total_comments"] == 1
        assert [r["login"] for r in result["reviewers"]] == ["github-copilot[bot]"]

    def test_different_id_with_same_login_is_not_a_self_comment(self):
        result = self._run(
            review_comments=[
                _make_review_comment("shared-service", actor_id=101)
            ],
            pr_author="shared-service",
            pr_author_id=202,
        )
        assert result["total_comments"] == 1
