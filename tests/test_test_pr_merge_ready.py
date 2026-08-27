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
stale_dirty_suspected = _mod.stale_dirty_suspected
classify_tier = _mod.classify_tier


class TestScriptCommit:
    """Issue #2443: the readiness verdict carries the producing script's commit."""

    def test_returns_git_sha_from_relative_pathspec(self):
        script_path = "/repo/.claude/skills/github/scripts/pr/test_pr_merge_ready.py"
        completed = [
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="/repo\n", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="abc1234\n", stderr=""),
        ]

        with (
            patch.object(_mod, "__file__", script_path),
            patch.object(_mod.subprocess, "run", side_effect=completed) as run,
        ):
            assert _mod._script_commit() == "abc1234"

        log_call = run.call_args_list[2]
        assert log_call.args[0][-1] == ".claude/skills/github/scripts/pr/test_pr_merge_ready.py"
        assert not Path(log_call.args[0][-1]).is_absolute()
        assert log_call.kwargs["encoding"] == "utf-8"
        assert log_call.kwargs["errors"] == "replace"
        assert log_call.kwargs["env"]["LC_ALL"] == "C"

    def test_unknown_when_script_has_uncommitted_changes(self):
        script_path = "/repo/.claude/skills/github/scripts/pr/test_pr_merge_ready.py"
        completed = [
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="/repo\n", stderr=""),
            _mod.subprocess.CompletedProcess(
                ["git"],
                0,
                stdout=" M .claude/skills/github/scripts/pr/test_pr_merge_ready.py\n",
                stderr="",
            ),
        ]

        with (
            patch.object(_mod, "__file__", script_path),
            patch.object(_mod.subprocess, "run", side_effect=completed) as run,
        ):
            assert _mod._script_commit() == "unknown"

        assert len(run.call_args_list) == 2

    def test_unknown_when_git_unavailable(self):
        with patch.object(_mod.subprocess, "run", side_effect=OSError("no git")):
            assert _mod._script_commit() == "unknown"

    def test_unknown_when_output_blank(self):
        completed = [
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="/repo\n", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="\n", stderr=""),
        ]

        with (
            patch.object(
                _mod, "__file__",
                "/repo/.claude/skills/github/scripts/pr/test_pr_merge_ready.py",
            ),
            patch.object(_mod.subprocess, "run", side_effect=completed),
        ):
            assert _mod._script_commit() == "unknown"

    def test_showsignature_flag_suppressed(self):
        """The -c log.showSignature=false flag prevents GPG diagnostic contamination."""
        completed = [
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="/repo\n", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="abc1234\n", stderr=""),
        ]
        with (
            patch.object(
                _mod, "__file__",
                "/repo/.claude/skills/github/scripts/pr/test_pr_merge_ready.py",
            ),
            patch.object(_mod.subprocess, "run", side_effect=completed),
        ):
            result = _mod._script_commit()
            log_call = _mod.subprocess.run.call_args_list[-1].args[0]
            # The -c flag must appear so git never invokes GPG at all.
            assert "-c" in log_call
            assert "log.showSignature=false" in log_call
            assert result == "abc1234"

    def test_git_command_includes_showsignature_false_flag(self):
        """The -c log.showSignature=false flag must appear in the git log call."""
        completed = [
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="/repo\n", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            _mod.subprocess.CompletedProcess(["git"], 0, stdout="deadc0de\n", stderr=""),
        ]
        with (
            patch.object(
                _mod, "__file__",
                "/repo/.claude/skills/github/scripts/pr/test_pr_merge_ready.py",
            ),
            patch.object(_mod.subprocess, "run", side_effect=completed),
        ):
            _mod._script_commit()
            log_call = _mod.subprocess.run.call_args_list[-1].args[0]
            assert "-c" in log_call, "-c flag missing from git log call"
            idx = log_call.index("-c")
            assert log_call[idx + 1] == "log.showSignature=false"


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

    def test_behind_branch_not_ready(self):
        # issue #2157: a branch behind base cannot land and is not auto-updated
        # by auto-merge in this repo, so CanMerge must be False even when CI
        # passes and threads are clean.
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeStateStatus"] = "BEHIND"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["MergeStateStatus"] == "BEHIND"
        assert any("behind" in r.lower() for r in result["Reasons"])

    def test_blocked_state_blocks_by_default(self):
        # issue #2326 (supersedes the prior #2157 BLOCKED-is-ready behavior):
        # BLOCKED means GitHub's branch protection still refuses the merge
        # (missing review decision / unmet protection rule). Treating it as
        # ready produced a false ready signal observed on PR #2323 and
        # contradicted the repo's own four-condition merge gate. BLOCKED must
        # make CanMerge False by default, with the blocker named in Reasons,
        # while MergeStateStatus still surfaces the state for the agent.
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeStateStatus"] = "BLOCKED"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["MergeStateStatus"] == "BLOCKED"
        assert any("blocked" in r.lower() for r in result["Reasons"]), (
            f"a BLOCKED merge state must name the blocker; reasons: "
            f"{result['Reasons']}"
        )
        assert any(
            "branch protection" in r.lower() or "review" in r.lower()
            for r in result["Reasons"]
        ), (
            "blocker reason should name branch protection / missing review "
            f"decision; reasons: {result['Reasons']}"
        )

    def test_blocked_state_no_other_blockers_still_blocks(self):
        # The exact PR #2323 shape: OPEN, not draft, 0 unresolved threads,
        # 0 failing checks, 0 pending checks, but mergeStateStatus=BLOCKED.
        # Every other gate is clean, so without this fix CanMerge would be
        # True (the false ready signal #2326 reports). With the fix, the
        # only reason is the BLOCKED merge state.
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeStateStatus"] = "BLOCKED"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["UnresolvedThreads"] == 0
        assert result["FailedRequiredChecks"] == []
        assert result["PendingRequiredChecks"] == []
        assert result["CIPassing"] is True
        assert len(result["Reasons"]) == 1, (
            "BLOCKED should be the sole blocker on an otherwise-clean PR; "
            f"reasons: {result['Reasons']}"
        )

    def test_null_merge_state_status_normalizes_to_empty_string(self):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeStateStatus"] = None
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is True
        assert result["MergeStateStatus"] == ""
        assert result["Reasons"] == []

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

    def test_pr_not_found_exits_2(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="test_pr_merge_ready"):
            with patch(
                "test_pr_merge_ready.gh_graphql",
                return_value={"repository": {"pullRequest": None}},
            ):
                with pytest.raises(SystemExit) as exc:
                    check_merge_readiness("o", "r", 999)
            assert exc.value.code == 2
        # Boundary observability: failed paths must emit a structured
        # `op=merge_ready_failed reason=...` log line so an operator can
        # grep failures across scripts using a unified taxonomy.
        assert any(
            "op=merge_ready_failed" in r.message
            and "reason=pr_not_found" in r.message
            for r in caplog.records
        ), "merge_ready failure path must log op=merge_ready_failed reason=pr_not_found"

    def test_pr_not_found_via_could_not_resolve_exits_2(self, caplog):
        """gh_graphql RuntimeError with 'Could not resolve' maps to exit 2."""
        import logging
        with caplog.at_level(logging.WARNING, logger="test_pr_merge_ready"):
            with patch(
                "test_pr_merge_ready.gh_graphql",
                side_effect=RuntimeError("Could not resolve to a PullRequest"),
            ):
                with pytest.raises(SystemExit) as exc:
                    check_merge_readiness("o", "r", 999)
            assert exc.value.code == 2
        assert any(
            "op=merge_ready_failed" in r.message
            and "reason=pr_not_found" in r.message
            for r in caplog.records
        )

    def test_graphql_error_exits_3_with_log(self, caplog):
        """A non-'Could not resolve' RuntimeError exits 3 and logs reason=graphql_error."""
        import logging
        with caplog.at_level(logging.WARNING, logger="test_pr_merge_ready"):
            with patch(
                "test_pr_merge_ready.gh_graphql",
                side_effect=RuntimeError("rate limit exceeded"),
            ):
                with pytest.raises(SystemExit) as exc:
                    check_merge_readiness("o", "r", 42)
            assert exc.value.code == 3
        assert any(
            "op=merge_ready_failed" in r.message
            and "reason=graphql_error" in r.message
            for r in caplog.records
        )

    def test_threads_pagination_fallback_when_inline_truncated(self, caplog):
        """When totalCount > inline first:100, falls back to paginated helper
        and uses ``max(inline, paginated)`` as a floor.

        The merge-ready GraphQL query embeds a ``reviewThreads(first: 100)``
        page for round-trip economy. If a PR has more than 100 threads, that
        page is a lower bound; the code calls get_unresolved_review_threads
        for an exact count. Per the floor invariant added in 8ca3b0e8, the
        result is ``max(inline_unresolved, len(paginated))`` so a transport
        failure in the paginated call (returns []) does not silently zero
        the count when inline showed unresolved threads.

        This test exercises the realistic case: paginated returns MORE than
        inline (paginated saw all threads; inline was truncated to 100).
        """
        import logging
        pr_data = json.loads(json.dumps(_OPEN_PR))
        threads = pr_data["repository"]["pullRequest"]["reviewThreads"]
        threads["totalCount"] = 150
        # Inline first:100 page: 100 unresolved threads.
        threads["nodes"] = [
            {"id": f"PRRT_{i}", "isResolved": False} for i in range(100)
        ]

        # Paginated helper sees all 150 and reports 105 unresolved
        # (45 of the 150 happen to be resolved; not visible in inline).
        fake_unresolved = [
            {"id": f"PRRT_real_{i}", "isResolved": False} for i in range(105)
        ]
        with caplog.at_level(logging.INFO, logger="test_pr_merge_ready"):
            with patch(
                "test_pr_merge_ready.gh_graphql", return_value=pr_data,
            ), patch(
                "test_pr_merge_ready.get_unresolved_review_threads",
                return_value=fake_unresolved,
            ) as mock_paginated:
                result = check_merge_readiness("o", "r", 42, ignore_ci=True)

        mock_paginated.assert_called_once_with("o", "r", 42)
        assert result["UnresolvedThreads"] == 105, (
            "Pagination fallback should use paginated count when it exceeds "
            "the inline floor (105 paginated > 100 inline)"
        )
        assert any(
            "op=merge_ready_threads_paginating" in r.message
            for r in caplog.records
        ), "Fallback path must log the paginating signal"

    def test_threads_pagination_fallback_floor_on_transport_failure(self):
        """Pagination floor invariant: when get_unresolved_review_threads
        returns [] (transport error per its 'never raises' contract), the
        unresolved count falls back to the inline-page count rather than
        silently zeroing. Codifies the 8ca3b0e8 fix.
        """
        pr_data = json.loads(json.dumps(_OPEN_PR))
        threads = pr_data["repository"]["pullRequest"]["reviewThreads"]
        threads["totalCount"] = 150
        # 42 unresolved, 58 resolved on inline page.
        threads["nodes"] = (
            [{"id": f"u{i}", "isResolved": False} for i in range(42)]
            + [{"id": f"r{i}", "isResolved": True} for i in range(58)]
        )

        with patch(
            "test_pr_merge_ready.gh_graphql", return_value=pr_data,
        ), patch(
            "test_pr_merge_ready.get_unresolved_review_threads",
            return_value=[],  # simulate transport-failure []
        ):
            result = check_merge_readiness("o", "r", 42, ignore_ci=True)

        assert result["UnresolvedThreads"] == 42, (
            "Floor invariant: paginated [] (transport error) must fall back "
            "to inline_unresolved_count, not silently zero"
        )

    def test_cancelled_with_later_success_does_not_block(self):
        """PR #1887 false-FAIL pattern: a CANCELLED debounce row plus a later
        SUCCESS row for the same check name was reported as a failed required
        check. After dedupe, the verdict for that name is OK and CanMerge is
        True. The retrospective records four false-FAIL reports caused by
        this exact pattern.
        """
        pr_data = json.loads(json.dumps(_OPEN_PR))
        commit = pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "ci/build",
                "status": "COMPLETED",
                "conclusion": "CANCELLED",
                "isRequired": True,
            },
            {
                "__typename": "CheckRun",
                "name": "ci/build",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "isRequired": True,
            },
        ]
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)

        assert result["CanMerge"] is True, (
            f"CANCELLED+SUCCESS dedupe failed; reasons: {result['Reasons']}"
        )
        assert result["FailedRequiredChecks"] == [], (
            "ci/build was incorrectly reported as a failed required check"
        )
        assert result["CIPassing"] is True

    def test_cancelled_with_later_failure_blocks(self):
        """Counterpart to the OK case: CANCELLED + FAILURE on the same name
        must still report FAIL. The dedupe rule is "any FAILURE wins"; it
        must not let a CANCELLED row hide a real failure.
        """
        pr_data = json.loads(json.dumps(_OPEN_PR))
        commit = pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "ci/test",
                "status": "COMPLETED",
                "conclusion": "CANCELLED",
                "isRequired": True,
            },
            {
                "__typename": "CheckRun",
                "name": "ci/test",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "isRequired": True,
            },
        ]
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)

        assert result["CanMerge"] is False
        assert result["FailedRequiredChecks"] == ["ci/test"]

    def test_cancelled_only_does_not_block(self):
        """Edge case: a check name whose only conclusion is CANCELLED has no
        opinion and must not block. (Without a passing or failing run, the
        check has not produced a verdict; treating it as a failed required
        check is the bug the retrospective documents.)
        """
        pr_data = json.loads(json.dumps(_OPEN_PR))
        commit = pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "ci/lint",
                "status": "COMPLETED",
                "conclusion": "CANCELLED",
                "isRequired": True,
            },
        ]
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)

        assert result["FailedRequiredChecks"] == []
        assert result["CanMerge"] is True

    def test_pending_then_cancelled_then_success_is_ok(self):
        """Three-row case: an in-progress row, a cancelled supersedence, and
        a successful final run. Verdict is OK because SUCCESS exists and
        nothing is FAILURE.
        """
        pr_data = json.loads(json.dumps(_OPEN_PR))
        commit = pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "ci/build",
                "status": "IN_PROGRESS",
                "conclusion": "",
                "isRequired": True,
            },
            {
                "__typename": "CheckRun",
                "name": "ci/build",
                "status": "COMPLETED",
                "conclusion": "CANCELLED",
                "isRequired": True,
            },
            {
                "__typename": "CheckRun",
                "name": "ci/build",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "isRequired": True,
            },
        ]
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)

        assert result["CanMerge"] is True
        assert result["FailedRequiredChecks"] == []
        assert result["PendingRequiredChecks"] == []


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


# ---------------------------------------------------------------------------
# Tests: fetched_pages_complete pagination cliff signal
#
# The /pr-review completion gate's pass_when expression requires the
# script's output to include fetched_pages_complete=true. A partial fetch
# that happens to find no failing checks is not evidence that no failing
# checks exist; the flag exists so the gate can fail closed in that case.
# ---------------------------------------------------------------------------


def _pr_payload_with_totals(
    *,
    review_threads_total: int = 0,
    review_threads_nodes: list[dict] | None = None,
    contexts_total: int = 0,
    contexts_nodes: list[dict] | None = None,
) -> dict:
    """Synthetic GraphQL payload that exercises the totalCount-vs-nodes check."""
    return {
        "repository": {
            "pullRequest": {
                "number": 1,
                "state": "OPEN",
                "isDraft": False,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "reviewThreads": {
                    "totalCount": review_threads_total,
                    "nodes": review_threads_nodes or [],
                },
                "commits": {
                    "nodes": [
                        {
                            "commit": {
                                "statusCheckRollup": {
                                    "state": "SUCCESS",
                                    "contexts": {
                                        "totalCount": contexts_total,
                                        "nodes": contexts_nodes or [],
                                    },
                                },
                            },
                        },
                    ],
                },
            },
        },
    }


class TestFetchedPagesCompleteFlag:
    def test_complete_within_first_page(self):
        payload = _pr_payload_with_totals(
            review_threads_total=2,
            review_threads_nodes=[
                {"id": "t1", "isResolved": True},
                {"id": "t2", "isResolved": True},
            ],
            contexts_total=1,
            contexts_nodes=[
                {
                    "__typename": "CheckRun",
                    "name": "ci",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "isRequired": True,
                },
            ],
        )
        with patch("test_pr_merge_ready.gh_graphql", return_value=payload):
            result = check_merge_readiness("o", "r", 1)
        assert result["fetched_pages_complete"] is True
        assert result["CanMerge"] is True

    def test_incomplete_when_more_threads_than_returned(self):
        # totalCount > len(nodes): GitHub has more threads than we fetched.
        payload = _pr_payload_with_totals(
            review_threads_total=150,
            review_threads_nodes=[
                {"id": f"t{i}", "isResolved": True} for i in range(100)
            ],
            contexts_total=1,
            contexts_nodes=[
                {
                    "__typename": "CheckRun",
                    "name": "ci",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "isRequired": True,
                },
            ],
        )
        with patch("test_pr_merge_ready.gh_graphql", return_value=payload):
            result = check_merge_readiness("o", "r", 1)
        assert result["fetched_pages_complete"] is False

    def test_incomplete_when_more_contexts_than_returned(self):
        payload = _pr_payload_with_totals(
            review_threads_total=0,
            review_threads_nodes=[],
            contexts_total=200,
            contexts_nodes=[
                {
                    "__typename": "CheckRun",
                    "name": f"ci-{i}",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "isRequired": True,
                }
                for i in range(100)
            ],
        )
        with patch("test_pr_merge_ready.gh_graphql", return_value=payload):
            result = check_merge_readiness("o", "r", 1)
        assert result["fetched_pages_complete"] is False

    def test_pagination_resolves_truncation(self):
        # Inline page is truncated (totalCount=150 > 100 nodes) AND
        # hasNextPage=True with a real cursor: the script paginates
        # the remainder via a follow-up query and reports
        # fetched_pages_complete=True. This is the live-PR scenario:
        # accumulated CI runs grow past the inline 100-cap.
        first_page_nodes = [
            {
                "__typename": "CheckRun",
                "name": f"ci-{i}",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "isRequired": False,
            }
            for i in range(100)
        ]
        merge_ready_payload = {
            "repository": {
                "pullRequest": {
                    "number": 1,
                    "state": "OPEN",
                    "isDraft": False,
                    "mergeable": "MERGEABLE",
                    "mergeStateStatus": "CLEAN",
                    "reviewThreads": {"totalCount": 0, "nodes": []},
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "statusCheckRollup": {
                                        "state": "SUCCESS",
                                        "contexts": {
                                            "totalCount": 150,
                                            "pageInfo": {
                                                "hasNextPage": True,
                                                "endCursor": "cursor-1",
                                            },
                                            "nodes": first_page_nodes,
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        # Follow-up page: 50 more contexts, hasNextPage=False.
        followup_payload = {
            "repository": {
                "object": {
                    "statusCheckRollup": {
                        "contexts": {
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                            "nodes": [
                                {
                                    "__typename": "CheckRun",
                                    "name": f"ci-{i}",
                                    "status": "COMPLETED",
                                    "conclusion": "SUCCESS",
                                    "isRequired": False,
                                }
                                for i in range(100, 150)
                            ],
                        },
                    },
                },
            },
        }
        with patch(
            "test_pr_merge_ready.gh_graphql",
            side_effect=[merge_ready_payload, followup_payload],
        ):
            result = check_merge_readiness("o", "r", 1)
        assert result["fetched_pages_complete"] is True
        assert result["CIPassing"] is True
        assert result["CanMerge"] is True

    def test_pagination_failure_keeps_incomplete(self):
        # Same setup but the follow-up call raises RuntimeError. The
        # script must report fetched_pages_complete=False (fail closed).
        first_page_nodes = [
            {
                "__typename": "CheckRun",
                "name": f"ci-{i}",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "isRequired": False,
            }
            for i in range(100)
        ]
        merge_ready_payload = {
            "repository": {
                "pullRequest": {
                    "number": 1, "state": "OPEN", "isDraft": False,
                    "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                    "reviewThreads": {"totalCount": 0, "nodes": []},
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "statusCheckRollup": {
                                        "state": "SUCCESS",
                                        "contexts": {
                                            "totalCount": 150,
                                            "pageInfo": {
                                                "hasNextPage": True,
                                                "endCursor": "cursor-1",
                                            },
                                            "nodes": first_page_nodes,
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "test_pr_merge_ready.gh_graphql",
            side_effect=[
                merge_ready_payload,
                RuntimeError("transport failed"),
            ],
        ):
            result = check_merge_readiness("o", "r", 1)
        assert result["fetched_pages_complete"] is False

    def test_complete_with_failing_required_check(self):
        payload = _pr_payload_with_totals(
            review_threads_total=0,
            contexts_total=2,
            contexts_nodes=[
                {
                    "__typename": "CheckRun",
                    "name": "ci",
                    "status": "COMPLETED",
                    "conclusion": "FAILURE",
                    "isRequired": True,
                },
                {
                    "__typename": "CheckRun",
                    "name": "lint",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "isRequired": True,
                },
            ],
        )
        with patch("test_pr_merge_ready.gh_graphql", return_value=payload):
            result = check_merge_readiness("o", "r", 1)
        assert result["fetched_pages_complete"] is True
        assert result["CIPassing"] is False
        assert "ci" in result["FailedRequiredChecks"]
        assert result["CanMerge"] is False


# ---------------------------------------------------------------------------
# Tests: stale_dirty_suspected (issue #2368)
# ---------------------------------------------------------------------------


class TestStaleDirtySuspected:
    @pytest.mark.parametrize(
        ("mergeable", "merge_state_status"),
        [
            ("CONFLICTING", "DIRTY"),       # both signals present
            ("CONFLICTING", "CLEAN"),       # mergeable signal alone
            ("MERGEABLE", "DIRTY"),         # state signal alone
        ],
    )
    def test_flags_dirty_or_conflicting(self, mergeable, merge_state_status):
        assert stale_dirty_suspected(mergeable, merge_state_status) is True

    @pytest.mark.parametrize(
        ("mergeable", "merge_state_status"),
        [
            ("MERGEABLE", "CLEAN"),         # the clean baseline
            ("MERGEABLE", "BLOCKED"),       # awaiting review, not a conflict
            ("MERGEABLE", "BEHIND"),        # behind != dirty; BEHIND has its own gate
            ("UNKNOWN", "UNKNOWN"),         # still computing, not yet a conflict
            ("", ""),                       # missing fields default to not-suspected
        ],
    )
    def test_does_not_flag_non_conflict_states(self, mergeable, merge_state_status):
        assert stale_dirty_suspected(mergeable, merge_state_status) is False


class TestStaleDirtyInMergeReadiness:
    def test_conflicting_sets_advisory_flag(self):
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeable"] = "CONFLICTING"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["StaleDirtySuspected"] is True

    def test_advisory_does_not_relax_can_merge(self):
        # The advisory is informational only. A CONFLICTING PR must still be
        # blocked; the caller verifies against local git before any refresh.
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeable"] = "CONFLICTING"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["StaleDirtySuspected"] is True
        assert result["CanMerge"] is False

    def test_clean_pr_does_not_set_advisory_flag(self):
        with patch("test_pr_merge_ready.gh_graphql", return_value=_OPEN_PR):
            result = check_merge_readiness("o", "r", 42)
        assert result["StaleDirtySuspected"] is False
        assert result["CanMerge"] is True


# ---------------------------------------------------------------------------
# Issue #4499: same-run sibling jobs must not mask each other
# ---------------------------------------------------------------------------

_R_A = "https://github.com/o/r/actions/runs/30827748904/job/91733674289"
_R_A2 = "https://github.com/o/r/actions/runs/30827748904/job/91733675289"
_R_B = "https://github.com/o/r/actions/runs/30826833314/job/91730700818"
_R_B2 = "https://github.com/o/r/actions/runs/30826833314/job/91730702341"


def _run_row(conclusion, details, status="COMPLETED"):
    return {"status": status, "conclusion": conclusion, "detailsUrl": details}


class TestCheckRunVerdictSameRunSiblings:
    def test_failure_and_skipped_in_one_run_fails(self):
        rows = [_run_row("FAILURE", _R_A), _run_row("SKIPPED", _R_A2)]
        assert _mod._check_run_verdict(rows) == "FAIL"

    def test_pr_4463_shape_two_runs_each_failure_plus_skipped(self):
        """The live shape that produced CIPassing=true against a red PR."""
        rows = [
            _run_row("FAILURE", _R_A), _run_row("FAILURE", _R_B),
            _run_row("SKIPPED", _R_A2), _run_row("SKIPPED", _R_B2),
        ]
        assert _mod._check_run_verdict(rows) == "FAIL"

    def test_later_rerun_success_supersedes_stale_failure_across_runs(self):
        """Issue #2208 must not regress."""
        rows = [_run_row("FAILURE", _R_B), _run_row("SUCCESS", _R_A)]
        assert _mod._check_run_verdict(rows) == "OK"

    def test_later_run_failure_beats_older_success_across_runs(self):
        rows = [_run_row("SUCCESS", _R_B), _run_row("FAILURE", _R_A)]
        assert _mod._check_run_verdict(rows) == "FAIL"

    def test_all_passing_siblings_in_one_run_is_ok(self):
        rows = [_run_row("SUCCESS", _R_A), _run_row("SKIPPED", _R_A2)]
        assert _mod._check_run_verdict(rows) == "OK"

    def test_rows_without_run_id_keep_prior_precedence(self):
        rows = [_run_row("FAILURE", ""), _run_row("SUCCESS", "")]
        assert _mod._check_run_verdict(rows) == "OK"

    def test_cancelled_sibling_still_carries_no_opinion(self):
        rows = [_run_row("CANCELLED", _R_A), _run_row("SUCCESS", _R_A2)]
        assert _mod._check_run_verdict(rows) == "OK"

    def test_cancelled_only_group_is_skip(self):
        rows = [_run_row("CANCELLED", _R_A), _run_row("CANCELLED", _R_A2)]
        assert _mod._check_run_verdict(rows) == "SKIP"

    def test_later_cancelled_run_does_not_mask_older_failure(self):
        rows = [_run_row("FAILURE", _R_B), _run_row("CANCELLED", _R_A)]
        assert _mod._check_run_verdict(rows) == "FAIL"

    def test_pending_sibling_does_not_hide_same_run_failure(self):
        rows = [
            _run_row("FAILURE", _R_A),
            _run_row("", _R_A2, status="IN_PROGRESS"),
        ]
        assert _mod._check_run_verdict(rows) == "FAIL"

    def test_pending_only_group_is_pending(self):
        rows = [_run_row("", _R_A, status="IN_PROGRESS")]
        assert _mod._check_run_verdict(rows) == "PENDING"

    def test_empty_rows_is_skip(self):
        assert _mod._check_run_verdict([]) == "SKIP"


class TestQuerySelectsDetailsUrl:
    """The run-partition is vacuous unless the query asks for detailsUrl.

    Both CheckRun selections must request it. Dropping either one silently
    turns every row into an unknown-provenance singleton, restoring the
    issue #4499 fail-open with no test failure anywhere else.
    """

    def test_both_check_run_selections_request_details_url(self):
        assert "detailsUrl" in _mod._CONTEXTS_PAGE_QUERY
        assert "detailsUrl" in _mod._MERGE_READY_QUERY


# ---------------------------------------------------------------------------
# Tests: Non-required failure disposition (issue #4902)
# ---------------------------------------------------------------------------

_load_dispositions = _mod._load_dispositions
_check_nonrequired_dispositions = _mod._check_nonrequired_dispositions
_VALID_DISPOSITIONS = _mod._VALID_DISPOSITIONS


class TestNonRequiredDispositions:
    """Issue #4902: require evidence before accepting nonrequired failures."""

    # -- Positive: disposed failures pass --

    def test_no_failures_returns_empty(self):
        assert _check_nonrequired_dispositions([], None) == []

    def test_all_failures_disposed_returns_empty(self, tmp_path):
        disp_file = tmp_path / "dispositions.json"
        disp_file.write_text(json.dumps({
            "Run Tests": {
                "disposition": "known-flaky",
                "reason": "Flaky network test tracked in #1234",
            },
        }))
        result = _check_nonrequired_dispositions(
            ["Run Tests"], str(disp_file),
        )
        assert result == []

    # -- Negative: undisposed failures block --

    def test_missing_file_returns_all_failures(self):
        result = _check_nonrequired_dispositions(
            ["Run Tests", "Lint"], "/nonexistent/path.json",
        )
        assert result == ["Run Tests", "Lint"]

    def test_none_file_returns_all_failures(self):
        result = _check_nonrequired_dispositions(
            ["Run Tests"], None,
        )
        assert result == ["Run Tests"]

    def test_partial_disposition_returns_undisposed(self, tmp_path):
        disp_file = tmp_path / "dispositions.json"
        disp_file.write_text(json.dumps({
            "Run Tests": {
                "disposition": "known-flaky",
                "reason": "Tracked in #1234",
            },
        }))
        result = _check_nonrequired_dispositions(
            ["Run Tests", "Lint"], str(disp_file),
        )
        assert result == ["Lint"]

    def test_invalid_disposition_value_treated_as_undisposed(self, tmp_path):
        disp_file = tmp_path / "dispositions.json"
        disp_file.write_text(json.dumps({
            "Run Tests": {
                "disposition": "yolo",
                "reason": "I want to merge",
            },
        }))
        result = _check_nonrequired_dispositions(
            ["Run Tests"], str(disp_file),
        )
        assert result == ["Run Tests"]

    def test_empty_reason_treated_as_undisposed(self, tmp_path):
        disp_file = tmp_path / "dispositions.json"
        disp_file.write_text(json.dumps({
            "Run Tests": {
                "disposition": "known-flaky",
                "reason": "",
            },
        }))
        result = _check_nonrequired_dispositions(
            ["Run Tests"], str(disp_file),
        )
        assert result == ["Run Tests"]

    # -- Edge cases --

    def test_malformed_json_returns_all_failures(self, tmp_path):
        disp_file = tmp_path / "dispositions.json"
        disp_file.write_text("not json{{{")
        result = _check_nonrequired_dispositions(
            ["Run Tests"], str(disp_file),
        )
        assert result == ["Run Tests"]

    def test_non_dict_entry_treated_as_undisposed(self, tmp_path):
        disp_file = tmp_path / "dispositions.json"
        disp_file.write_text(json.dumps({
            "Run Tests": "just a string",
        }))
        result = _check_nonrequired_dispositions(
            ["Run Tests"], str(disp_file),
        )
        assert result == ["Run Tests"]

    def test_all_valid_disposition_values_accepted(self, tmp_path):
        for disp_val in _VALID_DISPOSITIONS:
            disp_file = tmp_path / f"d_{disp_val}.json"
            disp_file.write_text(json.dumps({
                "Check": {"disposition": disp_val, "reason": "valid"},
            }))
            assert _check_nonrequired_dispositions(
                ["Check"], str(disp_file),
            ) == [], f"Failed for disposition={disp_val}"


class TestMergeReadinessWithDispositions:
    """Integration: check_merge_readiness blocks on undisposed failures."""

    def _pr_with_failed_nonrequired(self):
        """PR data: zero required checks, one failed non-required check."""
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeStateStatus"] = "UNSTABLE"
        pr_data["repository"]["pullRequest"]["commits"]["nodes"][0][
            "commit"
        ]["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "Run Python Tests",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "isRequired": False,
            },
        ]
        pr_data["repository"]["pullRequest"]["commits"]["nodes"][0][
            "commit"
        ]["statusCheckRollup"]["state"] = "FAILURE"
        return pr_data

    def test_undisposed_nonrequired_failure_blocks_merge(self):
        """Issue #4902 reproduction: UNSTABLE with no disposition must block."""
        pr_data = self._pr_with_failed_nonrequired()
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["UndisposedNonRequiredFailures"] == ["Run Python Tests"]
        assert any("disposition" in r for r in result["Reasons"])

    def test_disposed_nonrequired_failure_allows_merge(self, tmp_path):
        """With valid disposition file, UNSTABLE PR can merge."""
        pr_data = self._pr_with_failed_nonrequired()
        disp_file = tmp_path / "dispositions.json"
        disp_file.write_text(json.dumps({
            "Run Python Tests": {
                "disposition": "known-flaky",
                "reason": "Tracked in issue #9999",
            },
        }))
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness(
                "o", "r", 42,
                dispositions_file=str(disp_file),
            )
        assert result["CanMerge"] is True
        assert result["UndisposedNonRequiredFailures"] == []

    def test_zero_required_base_absent_check_blocks(self):
        """Zero required checks + failed non-required = blocked (no evidence)."""
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeStateStatus"] = "UNSTABLE"
        # No required checks at all, one non-required failure
        pr_data["repository"]["pullRequest"]["commits"]["nodes"][0][
            "commit"
        ]["statusCheckRollup"]["contexts"]["nodes"] = [
            {
                "__typename": "CheckRun",
                "name": "Purpose Check",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "isRequired": False,
            },
        ]
        pr_data["repository"]["pullRequest"]["commits"]["nodes"][0][
            "commit"
        ]["statusCheckRollup"]["state"] = "FAILURE"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        # Must block: zero required checks, non-required failed, no disposition
        assert result["CanMerge"] is False
        assert result["CIPassing"] is True  # no required checks failed
        assert "Purpose Check" in result["UndisposedNonRequiredFailures"]

    def test_clean_state_no_failures_still_passes(self):
        """Regression: CLEAN state with no failures should still pass."""
        with patch("test_pr_merge_ready.gh_graphql", return_value=_OPEN_PR):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is True
        assert result["UndisposedNonRequiredFailures"] == []


# ---------------------------------------------------------------------------
# Tier classification tests (issue #4899)
# ---------------------------------------------------------------------------


class TestClassifyTier:
    """Total tier classifier covers all mergeStateStatus values."""

    def test_clean_can_merge_is_t1(self):
        result = {
            "CanMerge": True,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "CLEAN",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "T1"

    def test_unstable_with_dispositions_is_t1(self):
        """UNSTABLE + all non-required disposed = T1 (PR #5033 model)."""
        result = {
            "CanMerge": True,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "UNSTABLE",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "T1"

    def test_unstable_undisposed_is_t2(self):
        """UNSTABLE with undisposed failures = T2 (CI work needed)."""
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "UNSTABLE",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": ["lint"],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "T2"

    def test_blocked_state(self):
        """BLOCKED mergeStateStatus maps to BLOCKED tier."""
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "BLOCKED",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "BLOCKED"

    def test_behind_state(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "BEHIND",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "BEHIND"

    def test_dirty_state(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "DIRTY",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "DIRTY"

    def test_draft_is_skip(self):
        result = {
            "CanMerge": False,
            "IsDraft": True,
            "State": "OPEN",
            "MergeStateStatus": "CLEAN",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "SKIP"

    def test_closed_is_skip(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "CLOSED",
            "MergeStateStatus": "",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "SKIP"

    def test_merged_is_skip(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "MERGED",
            "MergeStateStatus": "",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "SKIP"

    def test_ci_failures_only_is_t2(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "UNSTABLE",
            "FailedRequiredChecks": [{"name": "tests"}],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "T2"

    def test_threads_only_is_t3(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "CLEAN",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 3,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "T3"

    def test_ci_and_threads_is_t4(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "UNSTABLE",
            "FailedRequiredChecks": [{"name": "lint"}],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 2,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result) == "T4"

    def test_bot_with_failures_is_t5(self):
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "UNSTABLE",
            "FailedRequiredChecks": [{"name": "tests"}],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result, is_bot=True) == "T5"

    def test_bot_clean_is_t1(self):
        """Bot PRs that are fully clean still classify as T1."""
        result = {
            "CanMerge": True,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "CLEAN",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        assert classify_tier(result, is_bot=True) == "T1"

    def test_pending_required_only_is_t2(self):
        """Pending required checks with no failures = T2 (waiting on CI)."""
        result = {
            "CanMerge": False,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "CLEAN",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [{"name": "build"}],
        }
        assert classify_tier(result) == "T2"

    def test_tier_order_tuple_is_complete(self):
        """Verify _TIER_ORDER contains all possible classifier outputs."""
        from test_pr_merge_ready import _TIER_ORDER
        expected = {"T1", "T2", "T3", "T4", "T5", "BEHIND", "BLOCKED", "DIRTY", "SKIP"}
        assert set(_TIER_ORDER) == expected


class TestTierInMergeReadinessOutput:
    """Verify Tier field appears in check_merge_readiness output."""

    def test_tier_field_present_in_output(self):
        with patch("test_pr_merge_ready.gh_graphql", return_value=_OPEN_PR):
            result = check_merge_readiness("o", "r", 42)
        assert "Tier" in result
        assert result["Tier"] in _mod._TIER_ORDER


def _failing_bot_pr() -> dict:
    """`_OPEN_PR` with one failing required check, so a tier arm is reachable."""
    pr = json.loads(json.dumps(_OPEN_PR))
    node = pr["repository"]["pullRequest"]
    node["mergeStateStatus"] = "UNSTABLE"
    rollup = node["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
    rollup["state"] = "FAILURE"
    rollup["contexts"]["nodes"][0]["conclusion"] = "FAILURE"
    return pr


class TestIsBotFlagReachesTierT5:
    """`--is-bot` must change the tier, not merely arrive.

    `test_pr_autofix_bot_tier_forwarding.py` proves `/pr-autofix` puts the flag
    on the producer's argv, against a fake producer that records argv and
    prints whatever tier the case asked for. That is the whole forwarding
    contract on the command side and none of it on this side: a producer that
    accepted `--is-bot` and dropped it before `classify_tier` would leave every
    one of those cases green while issue #5208 stayed open, because no test in
    either suite runs argv through to an emitted tier.

    `TestClassifyTier.test_bot_with_failures_is_t5` calls `classify_tier`
    directly with `is_bot=True`, which skips the two wirings that can break:
    `build_parser`'s `--is-bot` into `args.is_bot`, and `main`'s `args.is_bot`
    into `check_merge_readiness(is_bot=...)` into `classify_tier`. These run the
    real `main` over the real code path with only `gh_graphql` faked, so all of
    it is exercised.
    """

    def _tier(self, argv: list[str], capsys) -> str:
        with patch("test_pr_merge_ready.assert_gh_authenticated"), patch(
            "test_pr_merge_ready.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("test_pr_merge_ready.gh_graphql", return_value=_failing_bot_pr()):
            rc = main(argv)
        assert rc == 1, "a PR with a failing required check is not merge-ready"
        return json.loads(capsys.readouterr().out)["Tier"]

    def test_the_is_bot_flag_produces_tier_t5(self, capsys):
        tier = self._tier(["--pull-request", "42", "--is-bot"], capsys)
        assert tier == "T5", (
            "the forwarded flag did not reach classify_tier, so /pr-autofix "
            f"sending --is-bot still cannot produce T5; got {tier}"
        )

    def test_without_the_flag_the_same_pr_is_not_t5(self, capsys):
        """Negative control. Without it, a hardcoded T5 would pass the case above.

        T2 is the arm this PR takes without the flag: a failing required check
        and no unresolved threads. That is exactly the misclassification issue
        #5208 reports, so this case also pins the defect's shape.
        """
        tier = self._tier(["--pull-request", "42"], capsys)
        assert tier == "T2", f"expected the pre-fix misclassification, got {tier}"
