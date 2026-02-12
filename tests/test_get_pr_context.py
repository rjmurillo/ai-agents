"""Tests for get_pr_context.py skill script."""

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


_mod = _import_script("get_pr_context")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _pr_json():
    return json.dumps({
        "number": 50,
        "title": "Test PR",
        "body": "Description",
        "headRefName": "feature",
        "baseRefName": "main",
        "state": "OPEN",
        "author": {"login": "alice"},
        "labels": [{"name": "bug"}],
        "reviewRequests": [],
        "commits": {"totalCount": 3},
        "additions": 10,
        "deletions": 5,
        "changedFiles": 2,
        "mergeable": "MERGEABLE",
        "mergedAt": None,
        "mergedBy": None,
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-02T00:00:00Z",
    })


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_flags(self):
        args = build_parser().parse_args([
            "--pull-request", "50", "--include-diff", "--diff-stat",
            "--include-changed-files",
        ])
        assert args.include_diff is True
        assert args.diff_stat is True
        assert args.include_changed_files is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_context.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with patch(
            "get_pr_context.assert_gh_authenticated",
        ), patch(
            "get_pr_context.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="not found"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_success_basic(self, capsys):
        with patch(
            "get_pr_context.assert_gh_authenticated",
        ), patch(
            "get_pr_context.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_pr_json(), rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["number"] == 50
        assert output["title"] == "Test PR"
        assert output["labels"] == ["bug"]
        assert output["diff"] is None
        assert output["files"] is None

    def test_include_diff(self, capsys):
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(stdout="diff output", rc=0)

        with patch(
            "get_pr_context.assert_gh_authenticated",
        ), patch(
            "get_pr_context.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-diff"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["diff"] == "diff output"

    def test_include_changed_files(self, capsys):
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=_pr_json(), rc=0)
            return _completed(stdout="file1.py\nfile2.py\n", rc=0)

        with patch(
            "get_pr_context.assert_gh_authenticated",
        ), patch(
            "get_pr_context.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--include-changed-files"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["files"] == ["file1.py", "file2.py"]
