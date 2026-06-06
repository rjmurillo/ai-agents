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


# ---------------------------------------------------------------------------
# Tests: enable_auto_merge error paths
# ---------------------------------------------------------------------------


class TestEnableAutoMergeErrors:
    """Regression tests for issue #2439 and friends.

    Each scenario hits the `enable_auto_merge` GraphQL mutation error branch
    and asserts the script surfaces an actionable message instead of a generic
    GraphQL failure.
    """

    def test_unstable_status_emits_actionable_fallback(self, capsys):
        """Issue #2439: UNSTABLE merge state must point to direct merge.

        When `mergeStateStatus == UNSTABLE` (e.g. a non-required check is
        failing), GitHub refuses auto-merge with "Pull request is in
        unstable status". The script must detect this and instruct the
        caller to fall back to merge_pr.py.
        """
        err = RuntimeError(
            "GraphQL request failed: gh: Pull request Pull request "
            "is in unstable status",
        )
        with patch("set_pr_auto_merge.gh_graphql", side_effect=err):
            with pytest.raises(SystemExit) as exc:
                enable_auto_merge("o", "r", 2431, "PR_abc", "SQUASH", "", "")
            # Exit 3 per ADR-035 (external/API error).
            assert exc.value.code == 3
        stderr = capsys.readouterr().err
        # Names the state explicitly so operators recognize it.
        assert "UNSTABLE" in stderr
        # Points to the documented fallback script.
        assert "merge_pr.py" in stderr
        # Includes the PR number so the suggested command is copy-pasteable.
        assert "2431" in stderr
        # Does NOT leak the raw GraphQL failure prefix as the only signal.
        assert "GraphQL request failed" not in stderr

    def test_auto_merge_not_allowed_emits_settings_hint(self, capsys):
        """Existing branch: 'Auto-merge is not allowed' -> repo settings hint.

        Locks in current behavior so the new UNSTABLE branch does not
        accidentally swallow it.
        """
        err = RuntimeError(
            "GraphQL request failed: Auto-merge is not allowed for this "
            "repository",
        )
        with patch("set_pr_auto_merge.gh_graphql", side_effect=err):
            with pytest.raises(SystemExit) as exc:
                enable_auto_merge("o", "r", 1, "PR_abc", "SQUASH", "", "")
            assert exc.value.code == 3
        stderr = capsys.readouterr().err
        assert "Settings" in stderr or "repository settings" in stderr

    def test_not_mergeable_emits_conflict_hint(self, capsys):
        """Existing branch: 'not mergeable' -> conflict hint."""
        err = RuntimeError(
            "GraphQL request failed: Pull request is not mergeable",
        )
        with patch("set_pr_auto_merge.gh_graphql", side_effect=err):
            with pytest.raises(SystemExit) as exc:
                enable_auto_merge("o", "r", 1, "PR_abc", "SQUASH", "", "")
            assert exc.value.code == 3
        stderr = capsys.readouterr().err
        assert "not in a mergeable state" in stderr

    def test_generic_graphql_failure_passed_through(self, capsys):
        """Unrecognized failures still surface the raw error for diagnosis."""
        err = RuntimeError("GraphQL request failed: something unexpected")
        with patch("set_pr_auto_merge.gh_graphql", side_effect=err):
            with pytest.raises(SystemExit) as exc:
                enable_auto_merge("o", "r", 1, "PR_abc", "SQUASH", "", "")
            assert exc.value.code == 3
        stderr = capsys.readouterr().err
        assert "Failed to enable auto-merge" in stderr
        assert "something unexpected" in stderr

    def test_clean_status_emits_actionable_fallback(self, capsys):
        """Issue #2450: CLEAN merge state must point to direct merge.

        When ``mergeStateStatus == CLEAN`` (all required checks pass,
        no unresolved reviews, no conflicts), GitHub refuses auto-merge
        with "Pull request is in clean status" because there is nothing
        for auto-merge to wait on. The script must detect this and
        instruct the caller to fall back to merge_pr.py instead of
        leaking the raw GraphQL prefix.
        """
        err = RuntimeError(
            "GraphQL request failed: gh: Pull request Pull request "
            "is in clean status",
        )
        with patch("set_pr_auto_merge.gh_graphql", side_effect=err):
            with pytest.raises(SystemExit) as exc:
                enable_auto_merge("o", "r", 2446, "PR_abc", "SQUASH", "", "")
            # Exit 3 per ADR-035 (external/API error).
            assert exc.value.code == 3
        stderr = capsys.readouterr().err
        # Names the state explicitly so operators recognize it.
        assert "CLEAN" in stderr
        # Points to the documented fallback script.
        assert "merge_pr.py" in stderr
        # Includes the PR number so the suggested command is copy-pasteable.
        assert "2446" in stderr
        # Does NOT leak the raw GraphQL failure prefix as the only signal.
        assert "GraphQL request failed" not in stderr

    def test_clean_status_fallback_propagates_merge_method(self, capsys):
        """CLEAN fallback must use the requested merge method, lowercased.

        Regression guard so a future refactor does not hard-code 'squash'
        in the suggested command when the caller passed MERGE or REBASE.
        """
        err = RuntimeError(
            "GraphQL request failed: gh: Pull request is in clean status",
        )
        with patch("set_pr_auto_merge.gh_graphql", side_effect=err):
            with pytest.raises(SystemExit):
                enable_auto_merge("o", "r", 99, "PR_abc", "REBASE", "", "")
        stderr = capsys.readouterr().err
        assert "--strategy rebase" in stderr

    def test_blocked_status_does_not_trigger_clean_or_unstable_fallback(
        self, capsys,
    ):
        """BLOCKED PRs (required reviews/checks pending) are auto-merge's
        intended use case. GitHub accepts ``enablePullRequestAutoMerge``
        for BLOCKED, so the success path must run with no CLEAN/UNSTABLE
        fallback ever triggering.

        This locks in that the CLEAN and UNSTABLE substring matchers do
        not over-match a BLOCKED state's accept path.
        """
        # Simulate a successful enable-auto-merge mutation on a BLOCKED PR.
        enable_data = {
            "enablePullRequestAutoMerge": {
                "pullRequest": {
                    "autoMergeRequest": {
                        "enabledAt": "2026-06-05T18:00:00Z",
                        "mergeMethod": "SQUASH",
                    },
                },
            },
        }
        with patch(
            "set_pr_auto_merge.gh_graphql",
            return_value=enable_data,
        ):
            rc = enable_auto_merge("o", "r", 2450, "PR_blk", "SQUASH", "", "")
        assert rc == 0
        captured = capsys.readouterr()
        # Must not have routed through either fallback message.
        assert "UNSTABLE merge state" not in captured.err
        assert "CLEAN merge state" not in captured.err
        # Confirms the normal enabled-summary printed.
        assert "Auto-merge enabled" in captured.out


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
