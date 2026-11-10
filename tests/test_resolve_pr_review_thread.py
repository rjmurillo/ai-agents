"""Tests for resolve_pr_review_thread.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("resolve_pr_review_thread")
main = _mod.main
build_parser = _mod.build_parser
resolve_review_thread = _mod.resolve_review_thread
get_unresolved_threads = _mod.get_unresolved_threads
query_thread_state = _mod.query_thread_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_thread_id_or_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_thread_id_and_pull_request_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--thread-id", "PRRT_abc", "--pull-request", "1"])

    def test_valid_thread_id(self):
        args = build_parser().parse_args(["--thread-id", "PRRT_abc123"])
        assert args.thread_id == "PRRT_abc123"

    def test_valid_pull_request_with_all(self):
        args = build_parser().parse_args(["--pull-request", "42", "--all"])
        assert args.pull_request == 42
        assert args.all is True


# ---------------------------------------------------------------------------
# Tests: resolve_review_thread
# ---------------------------------------------------------------------------


class TestResolveReviewThread:
    def test_success(self):
        with patch.object(
            _mod,
            "gh_graphql",
            return_value={"resolveReviewThread": {"thread": {"id": "t1", "isResolved": True}}},
        ):
            assert resolve_review_thread("PRRT_abc") is True

    def test_api_failure(self):
        with patch.object(
            _mod,
            "gh_graphql",
            side_effect=RuntimeError("API error"),
        ):
            assert resolve_review_thread("PRRT_abc") is False

    def test_not_resolved(self):
        with patch.object(
            _mod,
            "gh_graphql",
            return_value={"resolveReviewThread": {"thread": {"id": "t1", "isResolved": False}}},
        ):
            assert resolve_review_thread("PRRT_abc") is False


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch.object(
            _mod,
            "assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc"])
            assert exc.value.code == 4

    def test_single_thread_success(self):
        unresolved_state = {"id": "PRRT_abc", "isResolved": False}
        with (
            patch.object(
                _mod,
                "assert_gh_authenticated",
            ),
            patch.object(
                _mod,
                "query_thread_state",
                return_value=unresolved_state,
            ),
            patch.object(
                _mod,
                "resolve_review_thread",
                return_value=True,
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0

    def test_single_thread_failure(self, capsys):
        unresolved_state = {"id": "PRRT_abc", "isResolved": False}
        with (
            patch.object(
                _mod,
                "assert_gh_authenticated",
            ),
            patch.object(
                _mod,
                "query_thread_state",
                return_value=unresolved_state,
            ),
            patch.object(
                _mod,
                "resolve_review_thread",
                return_value=False,
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 1
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False
        assert output["Data"]["action"] == "ACT"
        assert output["Data"]["reason"] == "resolve_failed"

    def test_all_threads_already_resolved(self, capsys):
        with (
            patch.object(
                _mod,
                "assert_gh_authenticated",
            ),
            patch.object(
                _mod,
                "get_unresolved_threads",
                return_value=[],
            ),
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["total_unresolved"] == 0
        assert output["action"] == "SKIP"

    def test_all_threads_api_error(self):
        with (
            patch.object(
                _mod,
                "assert_gh_authenticated",
            ),
            patch.object(
                _mod,
                "get_unresolved_threads",
                side_effect=RuntimeError("API fail"),
            ),
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 3

    def test_all_threads_resolved_successfully(self, capsys):
        threads = [
            {
                "id": "PRRT_1",
                "isResolved": False,
                "comments": {
                    "nodes": [
                        {"databaseId": 100, "author": {"login": "user1"}},
                    ]
                },
            },
            {
                "id": "PRRT_2",
                "isResolved": False,
                "comments": {
                    "nodes": [
                        {"databaseId": 200, "author": {"login": "user2"}},
                    ]
                },
            },
        ]
        with (
            patch.object(
                _mod,
                "assert_gh_authenticated",
            ),
            patch.object(
                _mod,
                "get_unresolved_threads",
                return_value=threads,
            ),
            patch.object(
                _mod,
                "query_thread_state",
                side_effect=lambda thread_id: {
                    "id": thread_id,
                    "isResolved": False,
                    "pullRequest": {"number": 10},
                },
            ),
            patch.object(
                _mod,
                "resolve_review_thread",
                return_value=True,
            ),
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is True
        assert output["Data"]["resolved"] == 2
        assert output["Data"]["failed"] == 0

    def test_partial_resolution_returns_1(self, capsys):
        threads = [
            {
                "id": "PRRT_1",
                "isResolved": False,
                "comments": {
                    "nodes": [
                        {"databaseId": 100, "author": {"login": "user1"}},
                    ]
                },
            },
            {
                "id": "PRRT_2",
                "isResolved": False,
                "comments": {"nodes": []},
            },
        ]
        with (
            patch.object(
                _mod,
                "assert_gh_authenticated",
            ),
            patch.object(
                _mod,
                "get_unresolved_threads",
                return_value=threads,
            ),
            patch.object(
                _mod,
                "query_thread_state",
                side_effect=lambda thread_id: {
                    "id": thread_id,
                    "isResolved": False,
                    "pullRequest": {"number": 10},
                },
            ),
            patch.object(
                _mod,
                "resolve_review_thread",
                side_effect=[True, False],
            ),
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 1
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False
        assert output["Data"]["resolved"] == 1
        assert output["Data"]["failed"] == 1

    def test_thread_with_empty_comments(self, capsys):
        threads = [
            {
                "id": "PRRT_1",
                "isResolved": False,
                "comments": {"nodes": []},
            },
        ]
        with (
            patch.object(
                _mod,
                "assert_gh_authenticated",
            ),
            patch.object(
                _mod,
                "get_unresolved_threads",
                return_value=threads,
            ),
            patch.object(
                _mod,
                "query_thread_state",
                return_value={
                    "id": "PRRT_1",
                    "isResolved": False,
                    "pullRequest": {"number": 10},
                },
            ),
            patch.object(
                _mod,
                "resolve_review_thread",
                return_value=True,
            ),
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 0


# ---------------------------------------------------------------------------
# Tests: get_unresolved_threads
# ---------------------------------------------------------------------------


class TestGetUnresolvedThreads:
    def test_returns_unresolved_threads(self):
        repo_json = json.dumps({"owner": {"login": "o"}, "name": "r"})
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {"id": "t1", "isResolved": False, "comments": {"nodes": []}},
                            {"id": "t2", "isResolved": True, "comments": {"nodes": []}},
                            {"id": "t3", "isResolved": False, "comments": {"nodes": []}},
                        ],
                    },
                },
            },
        }
        with (
            patch(
                "subprocess.run",
                return_value=_completed(stdout=repo_json, rc=0),
            ),
            patch.object(
                _mod,
                "gh_graphql",
                return_value=graphql_data,
            ),
        ):
            result = get_unresolved_threads(42)
        assert len(result) == 2
        assert all(not t["isResolved"] for t in result)

    def test_repo_view_failure_raises(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="not logged in"),
        ):
            with pytest.raises(RuntimeError, match="Failed to get repo info"):
                get_unresolved_threads(42)

    def test_empty_threads_returns_empty(self):
        repo_json = json.dumps({"owner": {"login": "o"}, "name": "r"})
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [],
                    },
                },
            },
        }
        with (
            patch(
                "subprocess.run",
                return_value=_completed(stdout=repo_json, rc=0),
            ),
            patch.object(
                _mod,
                "gh_graphql",
                return_value=graphql_data,
            ),
        ):
            result = get_unresolved_threads(42)
        assert result == []

    def test_all_resolved_returns_empty(self):
        repo_json = json.dumps({"owner": {"login": "o"}, "name": "r"})
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {"id": "t1", "isResolved": True, "comments": {"nodes": []}},
                        ],
                    },
                },
            },
        }
        with (
            patch(
                "subprocess.run",
                return_value=_completed(stdout=repo_json, rc=0),
            ),
            patch.object(
                _mod,
                "gh_graphql",
                return_value=graphql_data,
            ),
        ):
            result = get_unresolved_threads(42)
        assert result == []


# ---------------------------------------------------------------------------
# Tests: query_thread_state
# ---------------------------------------------------------------------------


class TestQueryThreadState:
    def test_returns_thread_dict_when_found(self):
        node = {"id": "PRRT_abc", "isResolved": False, "pullRequest": {"number": 1}}
        with patch.object(
            _mod,
            "gh_graphql",
            return_value={"node": node},
        ):
            result = query_thread_state("PRRT_abc")
        assert result == node

    def test_returns_none_when_not_found(self):
        with patch.object(
            _mod,
            "gh_graphql",
            return_value={"node": None},
        ):
            result = query_thread_state("PRRT_missing")
        assert result is None

    def test_propagates_api_error(self):
        with patch.object(
            _mod,
            "gh_graphql",
            side_effect=RuntimeError("network error"),
        ):
            with pytest.raises(RuntimeError, match="network error"):
                query_thread_state("PRRT_abc")


# ---------------------------------------------------------------------------
# Tests: --all pagination (issue #7222, lossless-queue-reads.md)
# ---------------------------------------------------------------------------
def _threads_page(ids, *, resolved=False, cursor=None, has_next=False):
    return {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                    "nodes": [
                        {"id": i, "isResolved": resolved, "comments": {"nodes": []}} for i in ids
                    ],
                },
            },
        },
    }


_REPO_VIEW = _completed(stdout=json.dumps({"owner": {"login": "o"}, "name": "r"}))


class TestGetUnresolvedThreadsPagination:
    def test_zero_threads_returns_empty(self):
        with (
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", return_value=_threads_page([])),
        ):
            assert get_unresolved_threads(42) == []

    def test_exactly_one_full_page_makes_one_request(self):
        page = _threads_page([f"t{i}" for i in range(100)])
        with (
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", return_value=page) as gql,
        ):
            result = get_unresolved_threads(42)
        assert len(result) == 100
        assert gql.call_count == 1

    def test_101_threads_across_two_pages_reads_the_second_page(self):
        first = _threads_page(
            [f"t{i}" for i in range(100)], resolved=True, cursor="CUR1", has_next=True
        )
        second = _threads_page(["t100"], resolved=False)
        with (
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", side_effect=[first, second]) as gql,
        ):
            result = get_unresolved_threads(42)
        assert [t["id"] for t in result] == ["t100"]
        assert gql.call_args_list[0].args[1].get("cursor") is None
        assert gql.call_args_list[1].args[1]["cursor"] == "CUR1"

    def test_failure_on_page_two_raises(self):
        first = _threads_page(["t0"], cursor="CUR1", has_next=True)
        with (
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", side_effect=[first, RuntimeError("HTTP 502")]),
            pytest.raises(RuntimeError, match="HTTP 502"),
        ):
            get_unresolved_threads(42)

    def test_missing_cursor_raises(self):
        first = _threads_page(["t0"], cursor=None, has_next=True)
        with (
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", return_value=first),
            pytest.raises(RuntimeError, match="endCursor empty"),
        ):
            get_unresolved_threads(42)

    def test_query_declares_cursor_and_page_info(self):
        assert "$cursor: String" in _mod._THREADS_QUERY
        assert "after: $cursor" in _mod._THREADS_QUERY
        assert "hasNextPage" in _mod._THREADS_QUERY


class TestResolveAllFailsLoudOnIncompleteRead:
    def test_missing_cursor_exits_3_not_no_unresolved(self, capsys):
        first = _threads_page([f"t{i}" for i in range(100)], resolved=True, has_next=True)
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", return_value=first),
        ):
            rc = main(["--pull-request", "42", "--all", "--output-format", "json"])
        out = capsys.readouterr().out
        assert rc == 3
        assert "no_unresolved_threads" not in out
        assert "read 100 thread(s)" in out

    def test_unresolved_thread_on_page_two_is_resolved(self, capsys):
        first = _threads_page(
            [f"t{i}" for i in range(100)], resolved=True, cursor="CUR1", has_next=True
        )
        second = _threads_page(["t100"], resolved=False)
        with (
            patch.object(_mod, "assert_gh_authenticated"),
            patch("subprocess.run", return_value=_REPO_VIEW),
            patch.object(_mod, "gh_graphql", side_effect=[first, second]),
            patch.object(_mod, "_thread_decision", return_value=("ACT", "thread_unresolved")),
            patch.object(_mod, "resolve_review_thread", return_value=True) as resolve,
        ):
            rc = main(["--pull-request", "42", "--all", "--output-format", "json"])
        assert rc == 0
        resolve.assert_called_once_with("t100")
        assert json.loads(capsys.readouterr().out)["Data"]["resolved"] == 1
