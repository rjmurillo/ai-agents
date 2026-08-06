"""Tests for get_pr_reviewers.py skill script."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)
_MODULE = "get_pr_reviewers"
_SCRIPT = _SCRIPTS_DIR / f"{_MODULE}.py"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script(_MODULE)
main = _mod.main
build_parser = _mod.build_parser
_is_bot = _mod._is_bot


def _actor(
    login: str,
    account_id: int | None = None,
    actor_type: str = "User",
) -> dict:
    return {
        "__typename": actor_type,
        "login": login,
        "databaseId": account_id,
    }


def _comment(
    login: str,
    account_id: int | None = None,
    actor_type: str = "User",
) -> dict:
    return {
        "user": {
            "login": login,
            "id": account_id,
            "type": actor_type,
        }
    }


def _request_node(actor: dict | None) -> dict:
    return {"requestedReviewer": actor}


def _review_node(actor: dict | None) -> dict:
    return {"author": actor}


def _connection(nodes: list[dict], *, next_cursor: str | None = None) -> dict:
    return {
        "nodes": nodes,
        "pageInfo": {
            "hasNextPage": next_cursor is not None,
            "endCursor": next_cursor,
        },
    }


@contextmanager
def _api(
    *,
    author: dict | None = None,
    request_pages: list[dict] | None = None,
    review_pages: list[dict] | None = None,
    review_comments: list[dict] | None = None,
    issue_comments: list[dict] | None = None,
    graphql_error: RuntimeError | None = None,
    legacy_author: Any = None,
    legacy_error: BaseException | None = None,
):
    requests = list(request_pages or [_connection([])])
    reviews = list(review_pages or [_connection([])])
    request_index = 0
    review_index = 0

    def graphql(query: str, _variables: dict) -> dict:
        nonlocal request_index, review_index
        if graphql_error is not None:
            raise graphql_error
        if "reviewRequests" in query:
            page = requests[request_index]
            request_index += 1
            pull_request = {"author": author, "reviewRequests": page}
        else:
            page = reviews[review_index]
            review_index += 1
            pull_request = {"reviews": page}
        return {"repository": {"pullRequest": pull_request}}

    def rest(endpoint: str, **_kwargs) -> list[dict]:
        if "/pulls/" in endpoint:
            return review_comments or []
        return issue_comments or []

    if legacy_author is None:
        legacy_author = author.get("login", "") if isinstance(author, dict) else ""
    pr_view = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"author": {"login": legacy_author}}),
        stderr="",
    )

    with patch(f"{_MODULE}.assert_gh_authenticated"), patch(
        f"{_MODULE}.resolve_repo_params",
        return_value=RepoInfo(owner="o", repo="r"),
    ), patch(f"{_MODULE}.gh_graphql", side_effect=graphql), patch(
        f"{_MODULE}.gh_api_paginated",
        side_effect=rest,
    ), patch(
        f"{_MODULE}.subprocess.run",
        return_value=pr_view,
        side_effect=legacy_error,
    ):
        yield


def _output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_flags(self):
        args = build_parser().parse_args(
            ["--pull-request", "10", "--exclude-bots", "--exclude-author"]
        )
        assert args.pull_request == 10
        assert args.exclude_bots is True
        assert args.exclude_author is True


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
        assert "Get unique reviewers" in result.stdout

    def test_not_authenticated_exits_4(self):
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
        assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with _api(author=None), patch(
            f"{_MODULE}.gh_graphql",
            return_value={"repository": {"pullRequest": None}},
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
        assert exc.value.code == 2

    def test_graphql_failure_exits_3(self):
        with _api(graphql_error=RuntimeError("server error")):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
        assert exc.value.code == 3

    def test_legacy_author_timeout_exits_3(self):
        with _api(
            author=_actor("alice", 1),
            legacy_error=subprocess.TimeoutExpired("gh", 30),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])

        assert exc.value.code == 3

    @pytest.mark.parametrize("failing_endpoint", ["pulls", "issues"])
    def test_partial_rest_pagination_exits_3(self, failing_endpoint, capsys):
        def rest(endpoint: str, **_kwargs) -> list[dict]:
            if f"/{failing_endpoint}/" in endpoint:
                warnings.warn(
                    "GitHub API page 2 failed. Returning partial results.",
                    UserWarning,
                    stacklevel=2,
                )
                return [_comment("partial", 1)]
            return []

        with _api(author=_actor("alice", 1)), patch(
            f"{_MODULE}.gh_api_paginated",
            side_effect=rest,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])

        assert exc.value.code == 3
        assert '"success": true' not in capsys.readouterr().out.lower()

    def test_live_cli_shaped_actors_keep_database_ids(self, capsys):
        author = _actor("copilot-swe-agent", 198982749, "Bot")
        review = _actor("copilot-pull-request-reviewer", 175728472, "Bot")
        with _api(
            author=author,
            review_pages=[_connection([_review_node(review)])],
            legacy_author="app/copilot-swe-agent",
        ):
            assert main(["--pull-request", "3235"]) == 0
        output = _output(capsys)
        assert output["pr_author"] == "app/copilot-swe-agent"
        assert output["pr_author_id"] == 198982749
        assert output["pr_author_observed"] == "copilot-swe-agent"
        assert output["pr_author_canonical"] == "copilot-swe-agent[bot]"
        reviewer = output["reviewers"][0]
        assert reviewer["login"] == "github-copilot[bot]"
        assert reviewer["actor_ids"] == [175728472]

    def test_exclude_bots_filters_bots(self, capsys):
        with _api(
            author=_actor("alice", 1),
            review_comments=[_comment("dependabot[bot]", 2, "Bot")],
        ):
            assert main(["--pull-request", "10", "--exclude-bots"]) == 0
        assert _output(capsys)["reviewers"] == []

    def test_exclude_author_uses_database_id(self, capsys):
        author = _actor("Copilot", 198982749, "Bot")
        comments = [
            _comment("Copilot", 198982749, "Bot"),
            _comment("Copilot", 175728472, "Bot"),
        ]
        with _api(author=author, review_comments=comments):
            assert main(["--pull-request", "10", "--exclude-author"]) == 0
        output = _output(capsys)
        assert [reviewer["login"] for reviewer in output["reviewers"]] == [
            "github-copilot[bot]"
        ]

    def test_missing_comment_user_is_skipped(self, capsys):
        with _api(author=_actor("alice", 1), review_comments=[{"user": None}]):
            assert main(["--pull-request", "10"]) == 0
        assert _output(capsys)["total_reviewers"] == 0

    def test_missing_requested_reviewer_is_skipped(self, capsys):
        requests = _connection([_request_node(None)])
        with _api(author=_actor("alice", 1), request_pages=[requests]):
            assert main(["--pull-request", "10"]) == 0
        assert _output(capsys)["total_reviewers"] == 0

    def test_missing_review_author_is_skipped(self, capsys):
        reviews = _connection([_review_node(None)])
        with _api(author=_actor("alice", 1), review_pages=[reviews]):
            assert main(["--pull-request", "10"]) == 0
        assert _output(capsys)["total_reviewers"] == 0

    def test_reviewers_are_sorted_by_comment_count(self, capsys):
        comments = [_comment("bob", 2), _comment("alice", 1), _comment("alice", 1)]
        with _api(author=_actor("author", 3), review_comments=comments):
            assert main(["--pull-request", "10"]) == 0
        reviewers = _output(capsys)["reviewers"]
        assert [reviewer["login"] for reviewer in reviewers] == ["alice", "bob"]

    def test_aliases_collapse_across_graphql_and_rest(self, capsys):
        review = _actor("copilot-pull-request-reviewer", 175728472, "Bot")
        comments = [_comment("Copilot", 175728472, "Bot")]
        with _api(
            author=_actor("alice", 1),
            review_pages=[_connection([_review_node(review)])],
            review_comments=comments,
        ):
            assert main(["--pull-request", "10"]) == 0
        reviewer = _output(capsys)["reviewers"][0]
        assert reviewer["login"] == "github-copilot[bot]"
        assert sorted(reviewer["aliases"]) == [
            "Copilot",
            "copilot-pull-request-reviewer",
        ]
        assert reviewer["actor_ids"] == [175728472]

    def test_shared_copilot_login_is_separated_by_account_id(self, capsys):
        comments = [
            _comment("Copilot", 175728472, "Bot"),
            _comment("Copilot", 198982749, "Bot"),
        ]
        with _api(author=_actor("alice", 1), review_comments=comments):
            assert main(["--pull-request", "10"]) == 0
        reviewers = {r["login"]: r for r in _output(capsys)["reviewers"]}
        assert set(reviewers) == {
            "github-copilot[bot]",
            "copilot-swe-agent[bot]",
        }

    def test_shared_account_id_merges_different_logins(self, capsys):
        comments = [
            _comment("coderabbitai[bot]", 136622811, "Bot"),
            _comment("coderabbitai", 136622811, "Bot"),
        ]
        with _api(author=_actor("alice", 1), review_comments=comments):
            assert main(["--pull-request", "20"]) == 0

        reviewers = _output(capsys)["reviewers"]
        assert len(reviewers) == 1
        assert reviewers[0]["actor_ids"] == [136622811]
        assert sorted(reviewers[0]["aliases"]) == [
            "coderabbitai",
            "coderabbitai[bot]",
        ]

    def test_shared_login_keeps_distinct_account_ids_separate(self, capsys):
        comments = [
            _comment("shared-service", 101, "Bot"),
            _comment("shared-service", 202, "Bot"),
        ]
        with _api(author=_actor("alice", 1), review_comments=comments):
            assert main(["--pull-request", "20"]) == 0

        reviewers = _output(capsys)["reviewers"]
        assert len(reviewers) == 2
        assert {tuple(reviewer["actor_ids"]) for reviewer in reviewers} == {
            (101,),
            (202,),
        }

    def test_exclude_author_uses_id_when_aliases_differ(self, capsys):
        comments = [_comment("coderabbitai[bot]", 136622811, "Bot")]
        with _api(
            author=_actor("coderabbitai", 136622811, "Bot"),
            review_comments=comments,
        ):
            assert main(["--pull-request", "20", "--exclude-author"]) == 0

        assert _output(capsys)["reviewers"] == []

    def test_request_and_review_pagination(self, capsys):
        request_pages = [
            _connection([_request_node(_actor("alice", 1))], next_cursor="r2"),
            _connection([_request_node(_actor("bob", 2))]),
        ]
        review_pages = [
            _connection([_review_node(_actor("carol", 3))], next_cursor="v2"),
            _connection([_review_node(_actor("dave", 4))]),
        ]
        with _api(
            author=_actor("author", 5),
            request_pages=request_pages,
            review_pages=review_pages,
        ):
            assert main(["--pull-request", "10"]) == 0
        assert {r["login"] for r in _output(capsys)["reviewers"]} == {
            "alice",
            "bob",
            "carol",
            "dave",
        }

    @pytest.mark.parametrize("connection", ["requests", "reviews"])
    def test_repeated_pagination_cursor_exits_3(self, connection: str) -> None:
        repeated_pages = [
            _connection([], next_cursor="same"),
            _connection([], next_cursor="same"),
        ]
        request_pages = repeated_pages if connection == "requests" else None
        review_pages = repeated_pages if connection == "reviews" else None
        with _api(
            author=_actor("alice", 1),
            request_pages=request_pages,
            review_pages=review_pages,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])

        assert exc.value.code == 3

    @pytest.mark.parametrize("connection", ["requests", "reviews"])
    def test_missing_pagination_cursor_exits_3(self, connection):
        bad_page = {
            "nodes": [],
            "pageInfo": {"hasNextPage": True, "endCursor": None},
        }
        request_pages = [bad_page] if connection == "requests" else None
        review_pages = [bad_page] if connection == "reviews" else None
        with _api(
            author=_actor("alice", 1),
            request_pages=request_pages,
            review_pages=review_pages,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
        assert exc.value.code == 3

    @pytest.mark.parametrize("connection", ["requests", "reviews"])
    @pytest.mark.parametrize(
        "bad_page",
        [
            {},
            {"nodes": [], "pageInfo": {}},
            {"nodes": None, "pageInfo": {"hasNextPage": False}},
            {"nodes": [], "pageInfo": {"hasNextPage": None}},
        ],
    )
    def test_incomplete_graphql_connection_exits_3(
        self,
        connection: str,
        bad_page: dict,
    ) -> None:
        request_pages = [bad_page] if connection == "requests" else None
        review_pages = [bad_page] if connection == "reviews" else None
        with _api(
            author=_actor("alice", 1),
            request_pages=request_pages,
            review_pages=review_pages,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])

        assert exc.value.code == 3

    @pytest.mark.parametrize("location", ["author", "request", "review", "comment"])
    def test_non_string_actor_login_exits_3(self, location: str) -> None:
        malformed = {"__typename": "Bot", "login": 42, "databaseId": 1}
        author = malformed if location == "author" else _actor("alice", 1)
        request_pages = (
            [_connection([_request_node(malformed)])]
            if location == "request"
            else None
        )
        review_pages = (
            [_connection([_review_node(malformed)])]
            if location == "review"
            else None
        )
        review_comments = (
            [{"user": {"login": 42, "id": 1, "type": "Bot"}}]
            if location == "comment"
            else None
        )
        with _api(
            author=author,
            request_pages=request_pages,
            review_pages=review_pages,
            review_comments=review_comments,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])

        assert exc.value.code == 3


class TestIsBot:
    def test_bot_type(self):
        assert _is_bot("some-login", "Bot") is True

    def test_bot_suffix(self):
        assert _is_bot("dependabot[bot]", "User") is True

    def test_human(self):
        assert _is_bot("alice", "User") is False

    def test_empty_login_not_bot(self):
        assert _is_bot("", "User") is False
