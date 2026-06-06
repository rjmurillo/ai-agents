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


class TestScriptCommit:
    """Issue #2443: the readiness verdict carries the producing script's commit."""

    def test_returns_nonempty_string(self):
        sha = _mod._script_commit()
        assert isinstance(sha, str)
        assert sha

    def test_unknown_when_git_unavailable(self):
        with patch.object(_mod.subprocess, "run", side_effect=OSError("no git")):
            assert _mod._script_commit() == "unknown"

    def test_unknown_when_output_blank(self):
        completed = _mod.subprocess.CompletedProcess(["git"], 0, stdout="\n", stderr="")
        with patch.object(_mod.subprocess, "run", return_value=completed):
            assert _mod._script_commit() == "unknown"


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
