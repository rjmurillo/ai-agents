"""Tests for resolve_pr_review_thread.py --all pagination (issue #7222)."""

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
get_unresolved_threads = _mod.get_unresolved_threads


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


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
