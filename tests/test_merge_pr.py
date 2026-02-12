"""Tests for merge_pr.py skill script."""

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


_mod = _import_script("merge_pr")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_strategy_default(self):
        args = build_parser().parse_args(["--pull-request", "50"])
        assert args.strategy == "merge"

    def test_strategy_squash(self):
        args = build_parser().parse_args([
            "--pull-request", "50", "--strategy", "squash",
        ])
        assert args.strategy == "squash"

    def test_invalid_strategy(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([
                "--pull-request", "50", "--strategy", "invalid",
            ])


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "merge_pr.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="not found"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_already_merged_returns_0(self, capsys):
        state_json = json.dumps({
            "state": "MERGED", "mergeable": "", "mergeStateStatus": "", "headRefName": "f",
        })
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=state_json, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "none"

    def test_closed_pr_exits_6(self):
        state_json = json.dumps({
            "state": "CLOSED", "mergeable": "", "mergeStateStatus": "", "headRefName": "f",
        })
        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=state_json, rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 6

    def test_merge_success(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "merged"
        assert output["strategy"] == "merge"

    def test_auto_merge(self, capsys):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "MERGEABLE",
            "mergeStateStatus": "BLOCKED", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            rc = main(["--pull-request", "50", "--auto"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "auto-merge-enabled"
        assert output["state"] == "PENDING"

    def test_not_mergeable_exits_6(self):
        state_json = json.dumps({
            "state": "OPEN", "mergeable": "CONFLICTING",
            "mergeStateStatus": "DIRTY", "headRefName": "feature",
        })
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=1, stderr="not mergeable")

        with patch(
            "merge_pr.assert_gh_authenticated",
        ), patch(
            "merge_pr.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "subprocess.run",
            side_effect=_side_effect,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 6
