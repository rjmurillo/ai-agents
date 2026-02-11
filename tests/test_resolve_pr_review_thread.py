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


_mod = _import_script("resolve_pr_review_thread")
main = _mod.main
build_parser = _mod.build_parser
resolve_review_thread = _mod.resolve_review_thread
get_unresolved_threads = _mod.get_unresolved_threads


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
        with patch(
            "resolve_pr_review_thread.gh_graphql",
            return_value={"resolveReviewThread": {"thread": {"id": "t1", "isResolved": True}}},
        ):
            assert resolve_review_thread("PRRT_abc") is True

    def test_api_failure(self):
        with patch(
            "resolve_pr_review_thread.gh_graphql",
            side_effect=RuntimeError("API error"),
        ):
            assert resolve_review_thread("PRRT_abc") is False

    def test_not_resolved(self):
        with patch(
            "resolve_pr_review_thread.gh_graphql",
            return_value={"resolveReviewThread": {"thread": {"id": "t1", "isResolved": False}}},
        ):
            assert resolve_review_thread("PRRT_abc") is False


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "resolve_pr_review_thread.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc"])
            assert exc.value.code == 4

    def test_single_thread_success(self):
        with patch(
            "resolve_pr_review_thread.assert_gh_authenticated",
        ), patch(
            "resolve_pr_review_thread.gh_graphql",
            return_value={"resolveReviewThread": {"thread": {"id": "t1", "isResolved": True}}},
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0

    def test_single_thread_failure(self):
        with patch(
            "resolve_pr_review_thread.assert_gh_authenticated",
        ), patch(
            "resolve_pr_review_thread.gh_graphql",
            side_effect=RuntimeError("fail"),
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 1

    def test_all_threads_already_resolved(self, capsys):
        with patch(
            "resolve_pr_review_thread.assert_gh_authenticated",
        ), patch(
            "resolve_pr_review_thread.get_unresolved_threads",
            return_value=[],
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        # Output contains both plain text and JSON; extract last JSON block
        stdout = capsys.readouterr().out
        # Find JSON by looking for opening brace
        json_start = stdout.rfind("{")
        output = json.loads(stdout[json_start:])
        assert output["TotalUnresolved"] == 0

    def test_all_threads_api_error(self):
        with patch(
            "resolve_pr_review_thread.assert_gh_authenticated",
        ), patch(
            "resolve_pr_review_thread.get_unresolved_threads",
            side_effect=RuntimeError("API fail"),
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 3
