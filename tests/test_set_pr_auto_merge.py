"""Tests for set_pr_auto_merge.py skill script."""

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


_mod = _import_script("set_pr_auto_merge")
main = _mod.main
build_parser = _mod.build_parser
get_pr_node_id = _mod.get_pr_node_id
disable_auto_merge = _mod.disable_auto_merge
enable_auto_merge = _mod.enable_auto_merge


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--enable"])

    def test_enable_or_disable_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--pull-request", "1"])

    def test_enable_and_disable_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--pull-request", "1", "--enable", "--disable"])

    def test_valid_enable(self):
        args = build_parser().parse_args(["--pull-request", "42", "--enable"])
        assert args.pull_request == 42
        assert args.enable is True

    def test_merge_method_default(self):
        args = build_parser().parse_args(["--pull-request", "1", "--enable"])
        assert args.merge_method == "SQUASH"


# ---------------------------------------------------------------------------
# Tests: get_pr_node_id
# ---------------------------------------------------------------------------


class TestGetPrNodeId:
    def test_success(self):
        pr_data = {
            "repository": {
                "pullRequest": {
                    "id": "PR_abc",
                    "number": 42,
                    "state": "OPEN",
                    "autoMergeRequest": None,
                },
            },
        }
        with patch("set_pr_auto_merge.gh_graphql", return_value=pr_data):
            node_id, data = get_pr_node_id("o", "r", 42)
        assert node_id == "PR_abc"

    def test_pr_not_found_exits_2(self):
        with patch(
            "set_pr_auto_merge.gh_graphql",
            return_value={"repository": {"pullRequest": None}},
        ):
            with pytest.raises(SystemExit) as exc:
                get_pr_node_id("o", "r", 999)
            assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Tests: disable_auto_merge
# ---------------------------------------------------------------------------


class TestDisableAutoMerge:
    def test_already_disabled(self, capsys):
        pr_data = {"autoMergeRequest": None}
        rc = disable_auto_merge("o", "r", 42, "PR_abc", pr_data)
        assert rc == 0
        stdout = capsys.readouterr().out
        json_start = stdout.rfind("{")
        output = json.loads(stdout[json_start:])
        assert output["Action"] == "NoChange"

    def test_disable_success(self, capsys):
        pr_data = {"autoMergeRequest": {"enabledAt": "2024-01-01"}}
        with patch(
            "set_pr_auto_merge.gh_graphql",
            return_value={
                "disablePullRequestAutoMerge": {
                    "pullRequest": {"autoMergeRequest": None},
                },
            },
        ):
            rc = disable_auto_merge("o", "r", 42, "PR_abc", pr_data)
        assert rc == 0


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "set_pr_auto_merge.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--enable"])
            assert exc.value.code == 4

    def test_enable_success(self, capsys):
        pr_query_data = {
            "repository": {
                "pullRequest": {
                    "id": "PR_abc",
                    "number": 42,
                    "state": "OPEN",
                    "autoMergeRequest": None,
                },
            },
        }
        enable_data = {
            "enablePullRequestAutoMerge": {
                "pullRequest": {
                    "autoMergeRequest": {
                        "enabledAt": "2024-01-01T00:00:00Z",
                        "mergeMethod": "SQUASH",
                    },
                },
            },
        }
        with patch(
            "set_pr_auto_merge.assert_gh_authenticated",
        ), patch(
            "set_pr_auto_merge.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "set_pr_auto_merge.gh_graphql",
            side_effect=[pr_query_data, enable_data],
        ):
            rc = main(["--pull-request", "42", "--enable"])
        assert rc == 0
