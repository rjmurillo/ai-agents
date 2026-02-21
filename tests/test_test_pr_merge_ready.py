"""Tests for test_pr_merge_ready.py skill script."""

from __future__ import annotations

import importlib.util
import json
import sys
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


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("test_pr_merge_ready")
main = _mod.main
build_parser = _mod.build_parser
check_merge_readiness = _mod.check_merge_readiness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPEN_PR = {
    "repository": {
        "pullRequest": {
            "number": 42,
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "reviewThreads": {"totalCount": 0, "nodes": []},
            "commits": {
                "nodes": [
                    {
                        "commit": {
                            "statusCheckRollup": {
                                "state": "SUCCESS",
                                "contexts": {
                                    "nodes": [
                                        {
                                            "__typename": "CheckRun",
                                            "name": "build",
                                            "status": "COMPLETED",
                                            "conclusion": "SUCCESS",
                                            "isRequired": True,
                                        },
                                    ],
                                },
                            },
                        },
                    },
                ],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42

    def test_ignore_flags(self):
        args = build_parser().parse_args([
            "--pull-request", "1", "--ignore-ci", "--ignore-threads",
        ])
        assert args.ignore_ci is True
        assert args.ignore_threads is True


# ---------------------------------------------------------------------------
# Tests: check_merge_readiness
# ---------------------------------------------------------------------------


class TestCheckMergeReadiness:
    def test_ready_to_merge(self):
        with patch("test_pr_merge_ready.gh_graphql", return_value=_OPEN_PR):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is True
        assert result["Reasons"] == []

    def test_draft_pr_not_ready(self):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["isDraft"] = True
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert any("draft" in r.lower() for r in result["Reasons"])

    def test_merge_conflicts(self):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeable"] = "CONFLICTING"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert any("conflict" in r.lower() for r in result["Reasons"])

    def test_unresolved_threads(self):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["reviewThreads"] = {
            "totalCount": 2,
            "nodes": [
                {"id": "t1", "isResolved": False},
                {"id": "t2", "isResolved": True},
            ],
        }
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["UnresolvedThreads"] == 1

    def test_failed_required_check(self):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        commit = pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "build",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "isRequired": True,
            },
        ]
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["CIPassing"] is False

    def test_ignore_ci_flag(self):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        commit = pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "build",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "isRequired": True,
            },
        ]
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42, ignore_ci=True)
        assert result["CanMerge"] is True

    def test_pr_not_found_exits_2(self):
        with patch(
            "test_pr_merge_ready.gh_graphql",
            return_value={"repository": {"pullRequest": None}},
        ):
            with pytest.raises(SystemExit) as exc:
                check_merge_readiness("o", "r", 999)
            assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "test_pr_merge_ready.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_ready_returns_0(self, capsys):
        with patch(
            "test_pr_merge_ready.assert_gh_authenticated",
        ), patch(
            "test_pr_merge_ready.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merge_ready.gh_graphql",
            return_value=_OPEN_PR,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0

    def test_not_ready_returns_1(self, capsys):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["isDraft"] = True
        with patch(
            "test_pr_merge_ready.assert_gh_authenticated",
        ), patch(
            "test_pr_merge_ready.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merge_ready.gh_graphql",
            return_value=pr_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 1
