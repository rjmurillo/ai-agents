"""Tests for get_pr_review_threads.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.mock_fidelity import assert_mock_keys_match

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_pr_review_threads")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _graphql_response(threads=None, total_count=None):
    if threads is None:
        threads = []
    if total_count is None:
        total_count = len(threads)
    return json.dumps({
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "totalCount": total_count,
                        "nodes": threads,
                    },
                },
            },
        },
    })


def _thread(thread_id="PRRT_1", resolved=False, outdated=False, path="file.py",
            line=10, body="comment", author="alice"):
    return {
        "id": thread_id,
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": path,
        "line": line,
        "startLine": None,
        "diffSide": "RIGHT",
        "comments": {
            "totalCount": 1,
            "nodes": [
                {
                    "id": "C1",
                    "databaseId": 100,
                    "body": body,
                    "author": {"login": author},
                    "createdAt": "2025-01-01T00:00:00Z",
                    "updatedAt": "2025-01-01T00:00:00Z",
                },
            ],
        },
    }


def test_mock_thread_shape_matches_fixture():
    """Validate that the thread mock shape matches the canonical fixture."""
    thread = _thread()
    assert_mock_keys_match(thread, "review_thread", allow_extra=True)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_flags(self):
        args = build_parser().parse_args([
            "--pull-request", "50", "--unresolved-only", "--include-comments",
        ])
        assert args.unresolved_only is True
        assert args.include_comments is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="Could not resolve"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_success_all_threads(self, capsys):
        threads = [_thread("PRRT_1", resolved=False), _thread("PRRT_2", resolved=True)]
        response = _graphql_response(threads)
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert isinstance(output, dict)
        assert isinstance(output["total_threads"], int)
        assert output["total_threads"] == 2
        assert isinstance(output["unresolved_count"], int)
        assert output["unresolved_count"] == 1
        assert isinstance(output["resolved_count"], int)
        assert output["resolved_count"] == 1
        assert isinstance(output["threads"], list)

    def test_unresolved_only_filter(self, capsys):
        threads = [_thread("PRRT_1", resolved=False), _thread("PRRT_2", resolved=True)]
        response = _graphql_response(threads)
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50", "--unresolved-only"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert len(output["threads"]) == 1
        assert output["threads"][0]["is_resolved"] is False

    def test_include_comments(self, capsys):
        threads = [_thread("PRRT_1")]
        response = _graphql_response(threads)
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50", "--include-comments"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["threads"][0]["comments"] is not None
        assert len(output["threads"][0]["comments"]) == 1

    def test_empty_threads(self, capsys):
        response = _graphql_response([])
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["total_threads"] == 0
