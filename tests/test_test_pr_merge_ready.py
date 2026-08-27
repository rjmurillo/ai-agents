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
        # Contract change, issue #4899 reopen. This case previously asserted
        # CanMerge is True. GitHub declares mergeStateStatus non-null, so an
        # empty value means the probe did not return the state, not that the
        # state is benign, and the caller picks its merge path by that value.
        # Normalization to "" is unchanged; readiness on "" is what flipped.
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pr_data["repository"]["pullRequest"]["mergeStateStatus"] = None
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["MergeStateStatus"] == ""
        assert result["CanMerge"] is False
        assert any("<missing>" in reason for reason in result["Reasons"]), (
            f"a missing merge state must name itself; reasons: {result['Reasons']}"
        )

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
        expected = {
            "T1", "T2", "T3", "T4", "T5",
            "BEHIND", "BLOCKED", "DIRTY", "SKIP", "UNSUPPORTED",
        }
        assert set(_TIER_ORDER) == expected


def _add_unresolved_thread(pr_data):
    """Give `pr_data` exactly one unresolved review thread, in place."""
    threads = pr_data["repository"]["pullRequest"]["reviewThreads"]
    threads["nodes"].append({"id": "t-unresolved", "isResolved": False})
    threads["totalCount"] = len(threads["nodes"])


def _add_failed_required_check(pr_data, name="required-thing"):
    """Give `pr_data` exactly one failing required check, in place."""
    rollup = (
        pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        ["statusCheckRollup"]
    )
    rollup["contexts"]["nodes"].append({
        "__typename": "CheckRun",
        "name": name,
        "status": "COMPLETED",
        "conclusion": "FAILURE",
        "isRequired": True,
    })


def _clean_pr_in_state(merge_state):
    """An otherwise perfectly mergeable PR in `merge_state`.

    Threads resolved, required checks green, not draft, open, and
    `mergeable == "MERGEABLE"`, so `merge_state` is the only thing that can
    block. Without it every other gate passes and CanMerge is true.
    """
    pr_data = json.loads(json.dumps(_OPEN_PR))
    pr_data["repository"]["pullRequest"]["mergeStateStatus"] = merge_state
    return pr_data


class TestUnsupportedMergeStatesNeverReachT1:
    """Issue #4899 reopen: only a state with a merge path may reach T1.

    `.claude/commands/pr-autofix.md` "Ready-to-Merge Definition" item 4 reads:

        4. `mergeStateStatus` is `CLEAN` or `HAS_HOOKS` (or `UNSTABLE` with
           documented non-required failures).

    and its "Merge path by `mergeStateStatus`" table names a merge script for
    those three. Before this fix `_evaluate_pr_state` enumerated blockers
    (BEHIND, BLOCKED) instead of allowlisting, so any value nobody listed
    produced no reason, `CanMerge` was `len(reasons) == 0` and therefore true,
    and `classify_tier` returned T1: the auto-merge path, for a state
    pr-autofix has no verified handling for.
    """

    # Values with no row in pr-autofix.md's merge-path table, plus one GitHub
    # has not defined yet.  The last one is the point of the allowlist: an
    # enumeration of blockers cannot cover it.  HAS_HOOKS is deliberately NOT
    # here: GitHub defines it as "Mergeable with passing commit status and
    # pre-receive hooks", and `scripts/ci/check_pr_merge_state.py:27` lists it
    # in PASS_STATES, so it is covered by the positive cases below instead.
    _UNSUPPORTED = ("UNKNOWN", "DRAFT", "A_STATE_GITHUB_ADDS_LATER")

    def _clean_pr_in_state(self, merge_state):
        """See the module-level `_clean_pr_in_state`.

        Kept as a thin delegate so the cases below read unchanged while the
        negative-control class further down can build the same fixture without
        reaching into this class.
        """
        return _clean_pr_in_state(merge_state)

    @pytest.mark.parametrize("merge_state", _UNSUPPORTED)
    def test_unsupported_merge_state_blocks_can_merge(self, merge_state):
        pr_data = self._clean_pr_in_state(merge_state)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False, (
            f"{merge_state} has no merge path in pr-autofix.md and must not "
            f"report ready; reasons: {result['Reasons']}"
        )
        assert any(merge_state in reason for reason in result["Reasons"]), (
            f"the blocking reason must name the state; reasons: {result['Reasons']}"
        )

    @pytest.mark.parametrize("merge_state", _UNSUPPORTED)
    def test_unsupported_merge_state_is_never_t1(self, merge_state):
        pr_data = self._clean_pr_in_state(merge_state)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["Tier"] != "T1", (
            f"{merge_state} reached the auto-merge tier; that is issue #4899"
        )
        assert result["Tier"] in _mod._TIER_ORDER

    @pytest.mark.parametrize("merge_state", _UNSUPPORTED)
    def test_unsupported_merge_state_takes_its_own_terminal_tier(self, merge_state):
        """The tier the classifier actually chooses, not merely "not T1".

        `UNSUPPORTED` rather than `T4`: pr-autofix.md routes T3 and T4 into the
        round-cap thread-fix loop, and this PR has no threads and no CI
        failures, so that loop would have no action and would terminate only by
        burning the round cap and posting an escalation comment.
        """
        pr_data = self._clean_pr_in_state(merge_state)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["UnresolvedThreads"] == 0
        assert result["FailedRequiredChecks"] == []
        assert result["PendingRequiredChecks"] == []
        assert result["CIPassing"] is True
        assert result["Tier"] == "UNSUPPORTED"

    def test_unsupported_merge_state_with_threads_does_not_fall_through_to_t3(self):
        """The work-tier fallthrough, closed.

        Before the terminal tier, an unsupported state with threads classified
        T3, whose documented action ends in "then merge" for a state with no
        merge path. The state must win over the thread count.
        """
        pr_data = self._clean_pr_in_state("A_STATE_GITHUB_ADDS_LATER")
        _add_unresolved_thread(pr_data)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["UnresolvedThreads"] == 1
        assert result["Tier"] == "UNSUPPORTED"

    def test_unsupported_merge_state_with_a_failed_check_does_not_fall_through_to_t2(self):
        """The other half of the fallthrough: CI failures must not win either."""
        pr_data = self._clean_pr_in_state("A_STATE_GITHUB_ADDS_LATER")
        _add_failed_required_check(pr_data)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["FailedRequiredChecks"] == ["required-thing"]
        assert result["Tier"] == "UNSUPPORTED"

    def test_has_hooks_reaches_t1(self):
        """`HAS_HOOKS` is executable, so a clean PR in that state is T1.

        GitHub's GraphQL `MergeStateStatus` reference defines it as "Mergeable
        with passing commit status and pre-receive hooks", i.e. CLEAN plus
        pre-receive hooks, and `scripts/ci/check_pr_merge_state.py:27` carries
        `PASS_STATES = {"BEHIND", "BLOCKED", "CLEAN", "HAS_HOOKS",
        "UNSTABLE"}`. A PR on a repository with push rulesets reports
        `HAS_HOOKS` while fully green; blocking it stripped the author's armed
        auto-merge and burned rounds on a PR with nothing to fix.
        """
        pr_data = self._clean_pr_in_state("HAS_HOOKS")
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is True, f"reasons: {result['Reasons']}"
        assert result["Reasons"] == []
        assert result["Tier"] == "T1"

    def test_has_hooks_with_threads_is_t3(self):
        """A supported state still classifies by the work it needs.

        The T3 action ends in "then merge", which is only honest because
        HAS_HOOKS has a merge path. Paired with the UNSUPPORTED cases above,
        this is what separates "state has no path" from "state has a path and
        work remains".
        """
        pr_data = self._clean_pr_in_state("HAS_HOOKS")
        _add_unresolved_thread(pr_data)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["UnresolvedThreads"] == 1
        assert result["CanMerge"] is False
        assert result["Tier"] == "T3"

    def test_has_hooks_with_a_failed_required_check_is_t2(self):
        """The CI half of the pair above."""
        pr_data = self._clean_pr_in_state("HAS_HOOKS")
        _add_failed_required_check(pr_data)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["FailedRequiredChecks"] == ["required-thing"]
        assert result["CanMerge"] is False
        assert result["Tier"] == "T2"

    def test_dirty_merge_state_blocks_without_a_conflicting_mergeable(self):
        """DIRTY blocks on its own, not only via `mergeable == CONFLICTING`.

        The old code caught DIRTY indirectly through the separate `mergeable`
        field, so a response reporting the conflict in `mergeStateStatus` alone
        left `reasons` empty.

        Blocking here is the documented safe fallback, not a verdict that a
        real conflict exists: the comment on `_STALE_DIRTY_STATE` reads
        `mergeStateStatus == DIRTY` as a stale status cache, and
        `stale_dirty_suspected` already promised that absent a local refresh
        `CanMerge` stays False. The caller confirms against local git before
        treating the conflict as stale.
        """
        pr_data = self._clean_pr_in_state("DIRTY")
        assert pr_data["repository"]["pullRequest"]["mergeable"] == "MERGEABLE"
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["Tier"] == "DIRTY"

    @pytest.mark.parametrize("merge_state", ["CLEAN", "UNSTABLE"])
    def test_supported_merge_states_still_report_ready(self, merge_state):
        """Positive control: the allowlist must not block the real paths.

        Without this, a fix that blocked every state would pass every negative
        case above while breaking the feature outright. The third supported
        state, `HAS_HOOKS`, has its own case above carrying its citation.
        """
        pr_data = self._clean_pr_in_state(merge_state)
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is True, f"reasons: {result['Reasons']}"
        assert result["Reasons"] == []
        assert result["Tier"] == "T1"

    def test_unstable_with_disposed_non_required_failure_is_t1(self, tmp_path):
        """The `UNSTABLE` half of item 4: disposed non-required failures merge.

        A failing non-required check makes GitHub report UNSTABLE. With a
        recorded disposition it does not block, so this is the one case where a
        red check still reaches T1, and the allowlist must leave it intact.
        """
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pull_request = pr_data["repository"]["pullRequest"]
        pull_request["mergeStateStatus"] = "UNSTABLE"
        rollup = pull_request["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
        rollup["contexts"]["nodes"].append({
            "__typename": "CheckRun",
            "name": "flaky-extra",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "isRequired": False,
        })
        dispositions = {
            "flaky-extra": {
                "disposition": "known-flaky",
                "reason": "tracked in issue #4899",
            },
        }
        dispositions_path = tmp_path / "dispositions.json"
        dispositions_path.write_text(json.dumps(dispositions), encoding="utf-8")
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness(
                "o", "r", 42, dispositions_file=str(dispositions_path),
            )
        assert result["FailedNonRequiredChecks"] != []
        assert result["UndisposedNonRequiredFailures"] == []
        assert result["CanMerge"] is True, f"reasons: {result['Reasons']}"
        assert result["Tier"] == "T1"

    def test_undisposed_non_required_failure_on_unstable_is_t2(self):
        """Negative half of the pair above: no disposition, no T1."""
        pr_data = json.loads(json.dumps(_OPEN_PR))
        pull_request = pr_data["repository"]["pullRequest"]
        pull_request["mergeStateStatus"] = "UNSTABLE"
        rollup = pull_request["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
        rollup["contexts"]["nodes"].append({
            "__typename": "CheckRun",
            "name": "flaky-extra",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "isRequired": False,
        })
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["UndisposedNonRequiredFailures"] == ["flaky-extra"]
        assert result["CanMerge"] is False
        assert result["Tier"] == "T2"

    def test_draft_still_classifies_as_skip(self):
        """A draft is SKIP, not the unsupported-state tier.

        GitHub reports `mergeStateStatus == DRAFT` for a draft PR, which the
        allowlist blocks. `classify_tier` checks `IsDraft` first, so the draft
        must keep reaching SKIP rather than falling into a work tier.
        """
        pr_data = self._clean_pr_in_state("DRAFT")
        pr_data["repository"]["pullRequest"]["isDraft"] = True
        with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
            result = check_merge_readiness("o", "r", 42)
        assert result["CanMerge"] is False
        assert result["Tier"] == "SKIP"

    def test_supported_state_set_matches_the_documented_merge_gate(self):
        """The allowlist is exactly the set pr-autofix.md names a script for.

        Read from the command file rather than restated, so widening the set in
        the script without widening the documented merge path fails here.
        """
        assert _mod._SUPPORTED_MERGE_STATES == frozenset(
            {"CLEAN", "HAS_HOOKS", "UNSTABLE"}
        )
        command = (
            Path(__file__).resolve().parents[1]
            / ".claude" / "commands" / "pr-autofix.md"
        ).read_text(encoding="utf-8")
        assert (
            "`mergeStateStatus` is `CLEAN` or `HAS_HOOKS` (or `UNSTABLE` with "
            "documented non-required failures)."
        ) in command
        for state in _mod._SUPPORTED_MERGE_STATES:
            assert f"| `{state}`" in command or f"| `{state}` with" in command, (
                f"{state} is in the allowlist but has no row in the "
                f'"Merge path by `mergeStateStatus`" table'
            )


class TestTheAllowlistIsWhatBlocksTheUnsupportedStates:
    """Negative control: restore the pre-fix shape, watch the cases above fail.

    Every case in `TestUnsupportedMergeStatesNeverReachT1` asserts an outcome.
    None of them, alone, proves the outcome comes from this change rather than
    from a gate that already existed, and a test that passes identically before
    and after a fix is not evidence for the fix. The PR body records a manual
    revert-and-recount (12 failed, 96 passed). This class puts the same proof in
    the suite, where CI re-runs it: a control nobody re-runs stops being
    evidence the moment the code moves.

    What the fix replaced. `_evaluate_pr_state` enumerated blockers. Verbatim
    from `origin/main` at `.claude/skills/github/scripts/pr/`
    `test_pr_merge_ready.py`:

        merge_state = _merge_state_status(pr)
        if merge_state == "BEHIND":
            reasons.append("Branch is behind base; update against the base branch before merging")
        elif merge_state == "BLOCKED":
            reasons.append(
                "Merge blocked by branch protection (missing review decision or "
                "unmet protection rule)"
            )

    Any value nobody listed produced no reason. `CanMerge` is
    `len(reasons) == 0`, and `classify_tier` carried no allowlist guard, so such
    a state reached T1. The fix introduced `_SUPPORTED_MERGE_STATES` and made
    both `_append_merge_state_reason` and `classify_tier` read it.

    How the stand-in works, and what it is not. There is no pre-fix allowlist to
    revert to, so the control widens the allowlist to hold the one state under
    test. For that state this is exactly the pre-fix condition: no reason from
    `_append_merge_state_reason`, and `classify_tier`'s guard inert. It is a
    stand-in on the discriminating input, not a full revert of the diff.
    `BEHIND` and `BLOCKED` are refused by `_readiness_without_the_allowlist`
    below, because pre-fix those two blocked by explicit enumeration; widening
    the allowlist to hold them would model a defect that never existed.

    Measured, so the control is not merely asserted to work. Replacing the
    widening below with `frozenset(_mod._SUPPORTED_MERGE_STATES)`, a no-op, and
    re-running this class: 9 failed, 3 passed. The 9 are every case that
    reproduces the defect. The 3 still green are exactly the inverted control at
    the bottom, which the widening is supposed to leave untouched. So each case
    here moves on the allowlist and on nothing else.
    """

    _UNSUPPORTED = TestUnsupportedMergeStatesNeverReachT1._UNSUPPORTED
    _LATER = "A_STATE_GITHUB_ADDS_LATER"

    @staticmethod
    def _readiness_without_the_allowlist(pr_data, merge_state):
        """Run `check_merge_readiness` with `merge_state` no longer excluded."""
        assert merge_state not in ("BEHIND", "BLOCKED"), (
            "pre-fix, BEHIND and BLOCKED blocked by explicit enumeration, so "
            "widening the allowlist to hold either one models a defect that "
            "never existed"
        )
        widened = frozenset(_mod._SUPPORTED_MERGE_STATES | {merge_state})
        with (
            patch("test_pr_merge_ready.gh_graphql", return_value=pr_data),
            patch.object(_mod, "_SUPPORTED_MERGE_STATES", widened),
        ):
            return check_merge_readiness("o", "r", 42)

    @pytest.mark.parametrize("merge_state", _UNSUPPORTED)
    def test_without_the_allowlist_an_unsupported_state_reports_ready(self, merge_state):
        """Discriminates `test_unsupported_merge_state_blocks_can_merge`."""
        result = self._readiness_without_the_allowlist(
            _clean_pr_in_state(merge_state), merge_state,
        )
        assert result["Reasons"] == [], (
            "the pre-fix shape produced no blocking reason for an unlisted "
            "state; if it does now, this control no longer discriminates"
        )
        assert result["CanMerge"] is True

    @pytest.mark.parametrize("merge_state", _UNSUPPORTED)
    def test_without_the_allowlist_an_unsupported_state_reaches_t1(self, merge_state):
        """Discriminates the `is_never_t1` and `terminal_tier` cases.

        T1 is the auto-merge path, so this is issue #4899 itself, reproduced.
        """
        result = self._readiness_without_the_allowlist(
            _clean_pr_in_state(merge_state), merge_state,
        )
        assert result["Tier"] == "T1"

    def test_without_the_allowlist_threads_fall_through_to_t3(self):
        """Discriminates the thread half of the work-tier fallthrough.

        T3's documented action ends in "then merge", for a state with no merge
        path. That is what the terminal tier exists to prevent.
        """
        pr_data = _clean_pr_in_state(self._LATER)
        _add_unresolved_thread(pr_data)
        result = self._readiness_without_the_allowlist(pr_data, self._LATER)
        assert result["UnresolvedThreads"] == 1
        assert result["Tier"] == "T3"

    def test_without_the_allowlist_a_failed_check_falls_through_to_t2(self):
        """Discriminates the CI half of the same fallthrough."""
        pr_data = _clean_pr_in_state(self._LATER)
        _add_failed_required_check(pr_data)
        result = self._readiness_without_the_allowlist(pr_data, self._LATER)
        assert result["FailedRequiredChecks"] == ["required-thing"]
        assert result["Tier"] == "T2"

    def test_without_the_allowlist_dirty_reports_ready(self):
        """Discriminates `test_dirty_merge_state_blocks_without_a_conflicting_mergeable`.

        The tier stays `DIRTY` either way: `_MERGE_STATE_TIERS` carries a row
        for it and `classify_tier` reads that table before the allowlist guard.
        `CanMerge` is the half the fix moved, and it is the half that decides,
        because pr-autofix's four-condition gate reads `CanMerge`.
        """
        pr_data = _clean_pr_in_state("DIRTY")
        assert pr_data["repository"]["pullRequest"]["mergeable"] == "MERGEABLE"
        result = self._readiness_without_the_allowlist(pr_data, "DIRTY")
        assert result["CanMerge"] is True
        assert result["Tier"] == "DIRTY"

    @pytest.mark.parametrize("merge_state", ["CLEAN", "HAS_HOOKS", "UNSTABLE"])
    def test_the_widening_is_inert_for_states_already_in_the_allowlist(self, merge_state):
        """Inverted control: the stand-in must not pass by breaking everything.

        A stand-in that flipped every outcome would satisfy every case above
        while proving nothing about the allowlist. These three are already in
        `_SUPPORTED_MERGE_STATES`, so the widening is a no-op and they must
        still reach T1. The outcomes above therefore move because the state was
        excluded, not because patching the module attribute fires.
        """
        result = self._readiness_without_the_allowlist(
            _clean_pr_in_state(merge_state), merge_state,
        )
        assert result["CanMerge"] is True, f"reasons: {result['Reasons']}"
        assert result["Tier"] == "T1"


class TestTierInMergeReadinessOutput:
    """Verify Tier field appears in check_merge_readiness output."""

    def test_tier_field_present_in_output(self):
        with patch("test_pr_merge_ready.gh_graphql", return_value=_OPEN_PR):
            result = check_merge_readiness("o", "r", 42)
        assert "Tier" in result
        assert result["Tier"] in _mod._TIER_ORDER
