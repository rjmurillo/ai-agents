"""Tests for test_pr_merged.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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

# The GraphQL call now lives in the shared reader, not in this script (issue
# #4951). Patch it where it is defined, on the module object the script itself
# imported, so these tests exercise script + reader together rather than a
# second copy of the module tree.
_reader = sys.modules["github_core.pr_merge_state"]


def _patch_graphql(**kwargs):
    """Patch the single gh_graphql seam the script reaches through."""
    return patch.object(_reader, "gh_graphql", **kwargs)


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
        ), _patch_graphql(return_value=graphql_data):
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
        ), _patch_graphql(return_value=graphql_data):
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
        ), _patch_graphql(return_value=graphql_data):
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
        ), _patch_graphql(return_value=graphql_data):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_graphql_error_exits_3(self):
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), _patch_graphql(side_effect=RuntimeError("GraphQL failed")):
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
        ), _patch_graphql(return_value=graphql_data):
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
        ), _patch_graphql(return_value=graphql_data):
            rc = main(["--pull-request", "315", "--exit-zero-on-merged"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["merged"] is False


# ---------------------------------------------------------------------------
# Tests: probe failures are not merge answers (issue #4951)
# ---------------------------------------------------------------------------


class TestProbeFailures:
    """A failed probe must never be printed as ``"merged": false``.

    Before issue #4951 this script was the reliable reader and
    ``close_issue.py`` was the broken one. Both now share
    ``github_core.pr_merge_state``, so these cases pin the behavior that
    sharing is supposed to guarantee: when the remote says nothing usable,
    the script reports a failed call instead of a merge verdict.
    """

    @staticmethod
    def _run_expecting_exit(side_effect=None, return_value=None):
        kwargs = (
            {"side_effect": side_effect}
            if side_effect is not None
            else {"return_value": return_value}
        )
        with patch(
            "test_pr_merged.assert_gh_authenticated",
        ), patch(
            "test_pr_merged.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), _patch_graphql(**kwargs):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "4729"])
        return exc.value.code

    @pytest.mark.parametrize(
        "message",
        [
            "gh: Bad credentials (HTTP 401)",
            "gh: Requires authentication (HTTP 401)",
            "error: You are not logged into any GitHub hosts. "
            "To log in, run: gh auth login",
        ],
    )
    def test_auth_failure_exits_4(self, message):
        """Auth faults exit 4, the code the docstring always documented.

        Previously every RuntimeError from the query became exit 3, so a
        caller could not tell "fix your token" from "GitHub is having a bad
        day". ADR-035 separates them: 3 external, 4 auth.

        The parametrized strings are gh's own wording, not invented text, so
        they exercise github_core.api.AUTH_ERROR_MARKERS against what the CLI
        actually prints.
        """
        assert self._run_expecting_exit(side_effect=RuntimeError(message)) == 4

    def test_timeout_exits_3(self):
        """A timeout is an external failure, not a logic failure.

        ``subprocess.TimeoutExpired`` is not a ``RuntimeError``. Uncaught it
        would end the process with Python's exit 1, which ADR-035 reserves for
        a verified logic failure.
        """
        timeout = subprocess.TimeoutExpired(cmd=["gh", "api", "graphql"], timeout=30)
        assert self._run_expecting_exit(side_effect=timeout) == 3

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="no-repository"),
            pytest.param({"repository": None}, id="null-repository"),
            pytest.param({"repository": {}}, id="no-pull-request-field"),
            pytest.param(
                {"repository": {"pullRequest": {"state": "MERGED"}}},
                id="merged-field-absent",
            ),
            pytest.param(
                {"repository": {"pullRequest": {"merged": "true"}}},
                id="merged-field-not-boolean",
            ),
        ],
    )
    def test_malformed_payload_exits_3(self, payload, capsys):
        """A payload with no usable answer exits 3 and prints no verdict.

        The old code read ``pr.get("merged", False)``, so a response missing
        the field printed ``"merged": false`` and exited 0. That is a claim
        the remote never made.
        """
        assert self._run_expecting_exit(return_value=payload) == 3
        assert '"merged"' not in capsys.readouterr().out

    def test_error_message_never_says_not_merged(self, capsys):
        """The failure text must not describe a merge state it never read."""
        self._run_expecting_exit(side_effect=RuntimeError("connection reset"))
        assert "not merged" not in capsys.readouterr().err.lower()


class TestSharedReaderContract:
    """The GraphQL contract has exactly one home (issue #4951)."""

    def test_script_holds_no_private_query_copy(self):
        """A second copy of the query is a second contract that can drift."""
        source = (_SCRIPTS_DIR / "test_pr_merged.py").read_text(encoding="utf-8")
        assert "pullRequest(number: $prNumber)" not in source
        assert not hasattr(_mod, "_QUERY")

    def test_script_reads_through_the_shared_reader(self):
        assert _mod.read_pr_merge_state is _reader.read_pr_merge_state
