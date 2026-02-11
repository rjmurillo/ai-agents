"""Tests for get_thread_conversation_history.py skill script."""

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


_mod = _import_script("get_thread_conversation_history")
main = _mod.main
build_parser = _mod.build_parser
fetch_thread_comments = _mod.fetch_thread_comments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_thread_id_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--thread-id", "PRRT_abc"])
        assert args.thread_id == "PRRT_abc"

    def test_include_minimized_flag(self):
        args = build_parser().parse_args([
            "--thread-id", "PRRT_abc", "--include-minimized",
        ])
        assert args.include_minimized is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_invalid_thread_id_format_exits_1(self):
        with patch(
            "get_thread_conversation_history.assert_gh_authenticated",
        ), patch(
            "get_thread_conversation_history.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "INVALID"])
            assert exc.value.code == 1

    def test_empty_thread_id_exits_1(self):
        with patch(
            "get_thread_conversation_history.assert_gh_authenticated",
        ), patch(
            "get_thread_conversation_history.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "  "])
            assert exc.value.code == 1

    def test_successful_thread_fetch(self, capsys):
        gql_response = json.dumps({
            "data": {
                "node": {
                    "id": "PRRT_abc",
                    "isResolved": False,
                    "isOutdated": False,
                    "path": "src/main.py",
                    "line": 42,
                    "startLine": None,
                    "diffSide": "RIGHT",
                    "comments": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "PRRC_abc",
                                "databaseId": 100,
                                "body": "Fix this bug",
                                "author": {"login": "reviewer"},
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "isMinimized": False,
                                "minimizedReason": None,
                                "replyTo": None,
                            },
                        ],
                    },
                },
            },
        })
        with patch(
            "get_thread_conversation_history.assert_gh_authenticated",
        ), patch(
            "get_thread_conversation_history.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=gql_response, rc=0),
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is True
        assert output["ReturnedComments"] == 1

    def test_minimized_comments_filtered(self, capsys):
        gql_response = json.dumps({
            "data": {
                "node": {
                    "id": "PRRT_abc",
                    "isResolved": False,
                    "isOutdated": False,
                    "path": "src/main.py",
                    "line": 42,
                    "startLine": None,
                    "diffSide": "RIGHT",
                    "comments": {
                        "totalCount": 2,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "PRRC_1",
                                "databaseId": 100,
                                "body": "Visible",
                                "author": {"login": "user"},
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "isMinimized": False,
                                "minimizedReason": None,
                                "replyTo": None,
                            },
                            {
                                "id": "PRRC_2",
                                "databaseId": 101,
                                "body": "Hidden",
                                "author": {"login": "user"},
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "isMinimized": True,
                                "minimizedReason": "spam",
                                "replyTo": None,
                            },
                        ],
                    },
                },
            },
        })
        with patch(
            "get_thread_conversation_history.assert_gh_authenticated",
        ), patch(
            "get_thread_conversation_history.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=gql_response, rc=0),
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["ReturnedComments"] == 1
        assert output["MinimizedExcluded"] == 1

    def test_thread_not_found_exits_2(self):
        gql_response = json.dumps({"data": {"node": None}})
        with patch(
            "get_thread_conversation_history.assert_gh_authenticated",
        ), patch(
            "get_thread_conversation_history.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=gql_response, rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_nonexistent"])
            assert exc.value.code == 2
