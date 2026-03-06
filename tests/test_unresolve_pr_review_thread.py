"""Tests for unresolve_pr_review_thread.py skill script."""

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


_mod = _import_script("unresolve_pr_review_thread")
main = _mod.main
build_parser = _mod.build_parser
unresolve_review_thread = _mod.unresolve_review_thread
get_resolved_threads = _mod.get_resolved_threads


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

    def test_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--thread-id", "PRRT_abc", "--pull-request", "1"])

    def test_valid_thread_id(self):
        args = build_parser().parse_args(["--thread-id", "PRRT_abc123"])
        assert args.thread_id == "PRRT_abc123"


# ---------------------------------------------------------------------------
# Tests: unresolve_review_thread
# ---------------------------------------------------------------------------


class TestUnresolveReviewThread:
    def test_success(self):
        with patch(
            "unresolve_pr_review_thread.gh_graphql",
            return_value={"unresolveReviewThread": {"thread": {"id": "t1", "isResolved": False}}},
        ):
            assert unresolve_review_thread("PRRT_abc") is True

    def test_api_failure(self):
        with patch(
            "unresolve_pr_review_thread.gh_graphql",
            side_effect=RuntimeError("API error"),
        ):
            assert unresolve_review_thread("PRRT_abc") is False

    def test_still_resolved(self):
        with patch(
            "unresolve_pr_review_thread.gh_graphql",
            return_value={"unresolveReviewThread": {"thread": {"id": "t1", "isResolved": True}}},
        ):
            assert unresolve_review_thread("PRRT_abc") is False


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "unresolve_pr_review_thread.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc"])
            assert exc.value.code == 4

    def test_invalid_thread_id_exits_2(self):
        with patch(
            "unresolve_pr_review_thread.assert_gh_authenticated",
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "INVALID"])
            assert exc.value.code == 2

    def test_single_thread_success(self, capsys):
        with patch(
            "unresolve_pr_review_thread.assert_gh_authenticated",
        ), patch(
            "unresolve_pr_review_thread.gh_graphql",
            return_value={"unresolveReviewThread": {"thread": {"id": "t1", "isResolved": False}}},
        ):
            rc = main(["--thread-id", "PRRT_abc"])
        assert rc == 0
        stdout = capsys.readouterr().out
        # Script outputs plain text before JSON; extract JSON
        json_start = stdout.rfind("{")
        output = json.loads(stdout[json_start:])
        assert output["Success"] is True

    def test_all_threads_none_resolved(self, capsys):
        with patch(
            "unresolve_pr_review_thread.assert_gh_authenticated",
        ), patch(
            "unresolve_pr_review_thread.get_resolved_threads",
            return_value=[],
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        stdout = capsys.readouterr().out
        json_start = stdout.rfind("{")
        output = json.loads(stdout[json_start:])
        assert output["TotalResolved"] == 0

    def test_api_error_returns_3(self):
        with patch(
            "unresolve_pr_review_thread.assert_gh_authenticated",
        ), patch(
            "unresolve_pr_review_thread.get_resolved_threads",
            side_effect=RuntimeError("API fail"),
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 3
