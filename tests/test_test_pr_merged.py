"""Tests for test_pr_merged.py skill script."""

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


_mod = _import_script("test_pr_merged")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "315"])
        assert args.pull_request == 315
        assert args.exit_zero_on_merged is False
        assert args.exit_100_on_merged is False

    def test_exit_zero_on_merged_flag(self):
        args = build_parser().parse_args(
            ["--pull-request", "315", "--exit-zero-on-merged"],
        )
        assert args.exit_zero_on_merged is True

    def test_exit_100_on_merged_flag(self):
        args = build_parser().parse_args(
            ["--pull-request", "315", "--exit-100-on-merged"],
        )
        assert args.exit_100_on_merged is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "test_pr_merged.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_merged_returns_0(self, capsys):
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "state": "OPEN",
                    "merged": False,
                    "mergedAt": None,
                    "mergedBy": None,
                },
            },
        }
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merged.gh_graphql",
            return_value=graphql_data,
        ):
            rc = main(["--pull-request", "315"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["merged"] is False

    def test_pr_merged_returns_0_by_default(self, capsys):
        """Regression for issue #2308: a merged PR should exit 0 by default.

        The legacy exit-100 sentinel made successful merge verification look
        like a failed call to most shell/automation consumers. The default now
        matches the convention that exit 0 means "the question I asked was
        answered successfully", here, "yes, the PR is merged".

        Callers that want the historical skip-review-work sentinel can opt in
        with --exit-100-on-merged.
        """
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "state": "MERGED",
                    "merged": True,
                    "mergedAt": "2025-01-01T00:00:00Z",
                    "mergedBy": {"login": "admin"},
                },
            },
        }
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merged.gh_graphql",
            return_value=graphql_data,
        ):
            rc = main(["--pull-request", "315"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["merged"] is True
        assert output["merged_by"] == "admin"

    def test_pr_merged_with_exit_100_flag_returns_100(self, capsys):
        """--exit-100-on-merged restores the legacy skip-review sentinel."""
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "state": "MERGED",
                    "merged": True,
                    "mergedAt": "2025-01-01T00:00:00Z",
                    "mergedBy": {"login": "admin"},
                },
            },
        }
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merged.gh_graphql",
            return_value=graphql_data,
        ):
            rc = main(["--pull-request", "315", "--exit-100-on-merged"])
        assert rc == 100
        output = json.loads(capsys.readouterr().out)
        assert output["merged"] is True

    def test_pr_not_found_exits_2(self):
        graphql_data = {"repository": {"pullRequest": None}}
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merged.gh_graphql",
            return_value=graphql_data,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_graphql_error_exits_3(self):
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merged.gh_graphql",
            side_effect=RuntimeError("GraphQL failed"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 3

    def test_pr_merged_with_exit_zero_flag_returns_0(self, capsys):
        """--exit-zero-on-merged is a deprecated no-op (issue #2308).

        Originally introduced in #2277 to opt out of the exit-100 sentinel.
        After #2308 exit 0 is the default for any successful query, so this
        flag is a no-op preserved for backward compatibility.
        """
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "state": "MERGED",
                    "merged": True,
                    "mergedAt": "2025-01-01T00:00:00Z",
                    "mergedBy": {"login": "admin"},
                },
            },
        }
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merged.gh_graphql",
            return_value=graphql_data,
        ):
            rc = main(["--pull-request", "315", "--exit-zero-on-merged"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["merged"] is True
        assert output["merged_by"] == "admin"

    def test_pr_not_merged_with_exit_zero_flag_still_returns_0(self, capsys):
        """--exit-zero-on-merged does not change the not-merged path."""
        graphql_data = {
            "repository": {
                "pullRequest": {
                    "state": "OPEN",
                    "merged": False,
                    "mergedAt": None,
                    "mergedBy": None,
                },
            },
        }
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "test_pr_merged.gh_graphql",
            return_value=graphql_data,
        ):
            rc = main(["--pull-request", "315", "--exit-zero-on-merged"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["merged"] is False
