"""Tests for the --output-format flag of set_pr_auto_merge.py."""

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
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    # Registered under a private key so this file never replaces the
    # ``set_pr_auto_merge`` entry that test_set_pr_auto_merge.py patches by name.
    spec = importlib.util.spec_from_file_location(
        f"{name}_output_format", _SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{name}_output_format"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("set_pr_auto_merge")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Tests: --output-format
# ---------------------------------------------------------------------------

_PR_QUERY_DATA = {
    "repository": {
        "pullRequest": {"id": "PR_abc", "number": 42, "state": "OPEN", "autoMergeRequest": None},
    },
}
_ARMED_QUERY_DATA = {
    "repository": {
        "pullRequest": {
            "id": "PR_abc",
            "number": 42,
            "state": "OPEN",
            "autoMergeRequest": {"enabledAt": "2024-01-01T00:00:00Z", "mergeMethod": "SQUASH"},
        },
    },
}
_ENABLE_DATA = {
    "enablePullRequestAutoMerge": {
        "pullRequest": {
            "autoMergeRequest": {"enabledAt": "2024-01-01T00:00:00Z", "mergeMethod": "SQUASH"},
        },
    },
}
_DISABLE_DATA = {
    "disablePullRequestAutoMerge": {"pullRequest": {"autoMergeRequest": None}},
}
_STILL_ARMED_DATA = {
    "disablePullRequestAutoMerge": {
        "pullRequest": {"autoMergeRequest": {"enabledAt": "2024-01-01T00:00:00Z"}},
    },
}
_FAILED_ENABLE_DATA = {"enablePullRequestAutoMerge": {"pullRequest": {"autoMergeRequest": None}}}


def _run_main(argv, graphql_results):
    with (
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(_mod, "resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
        patch.object(_mod, "gh_graphql", side_effect=graphql_results),
    ):
        return main(argv)


class TestOutputFormat:
    def test_parser_accepts_each_format(self):
        for fmt in ("json", "human", "auto"):
            args = build_parser().parse_args(
                ["--pull-request", "1", "--enable", "--output-format", fmt]
            )
            assert args.output_format == fmt

    def test_parser_defaults_to_auto(self):
        args = build_parser().parse_args(["--pull-request", "1", "--enable"])
        assert args.output_format == "auto"

    def test_parser_rejects_unknown_format(self):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--pull-request", "1", "--enable", "--output-format", "xml"])
        assert exc.value.code == 2

    def test_enable_json_stdout_is_only_the_result_object(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--enable", "--output-format", "json"],
            [_PR_QUERY_DATA, _ENABLE_DATA],
        )
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Action"] == "Enabled"
        assert output["AutoMergeEnabled"] is True

    def test_enable_human_prints_summary_without_json(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--enable", "--output-format", "human"],
            [_PR_QUERY_DATA, _ENABLE_DATA],
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Auto-merge enabled for PR #42" in out
        assert "Method: SQUASH" in out
        assert "{" not in out

    def test_auto_without_a_terminal_emits_json(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--enable", "--output-format", "auto"],
            [_PR_QUERY_DATA, _ENABLE_DATA],
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["Success"] is True

    def test_disable_json_stdout_is_only_the_result_object(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--disable", "--output-format", "json"],
            [_ARMED_QUERY_DATA, _DISABLE_DATA],
        )
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Action"] == "Disabled"
        assert output["AutoMergeEnabled"] is False

    def test_disable_human_prints_summary_without_json(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--disable", "--output-format", "human"],
            [_ARMED_QUERY_DATA, _DISABLE_DATA],
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Auto-merge disabled for PR #42" in out
        assert "{" not in out

    def test_already_disabled_json_has_no_prose_line(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--disable", "--output-format", "json"],
            [_PR_QUERY_DATA],
        )
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["Action"] == "NoChange"

    def test_already_disabled_human_prints_prose_only(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--disable", "--output-format", "human"],
            [_PR_QUERY_DATA],
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Auto-merge is not enabled on PR #42" in out
        assert "{" not in out

    def test_disable_that_does_not_land_exits_1_and_reports_on_stderr(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--disable", "--output-format", "human"],
            [_ARMED_QUERY_DATA, _STILL_ARMED_DATA],
        )
        captured = capsys.readouterr()
        assert rc == 1
        assert captured.out == ""
        assert "Failed to disable auto-merge for PR #42" in captured.err

    def test_enable_that_does_not_land_exits_1_in_human_mode(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--enable", "--output-format", "human"],
            [_PR_QUERY_DATA, _FAILED_ENABLE_DATA],
        )
        captured = capsys.readouterr()
        assert rc == 1
        assert captured.out == ""
        assert "Failed to enable auto-merge for PR #42" in captured.err

    def test_enable_that_does_not_land_exits_1_in_json_mode(self, capsys):
        rc = _run_main(
            ["--pull-request", "42", "--enable", "--output-format", "json"],
            [_PR_QUERY_DATA, _FAILED_ENABLE_DATA],
        )
        captured = capsys.readouterr()
        assert rc == 1
        output = json.loads(captured.out)
        assert output["Success"] is False
        assert output["MergeMethod"] is None
