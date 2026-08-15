# taste-lint: ignore file-size, one suite shares GraphQL fixtures across all verdict states.
"""Tests for triage_red_check.py skill script (issue #5073).

Covers the three verdicts (GREEN_ON_MAIN exit 0, RED_ON_MAIN exit 1,
UNKNOWN exit 3), config and API failure paths, and the two recorded traps:
job-name collisions across workflows and SKIPPED rows masking SUCCESS.
The GitHub API boundary (gh_graphql, auth, repo resolution) is mocked.
"""

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
    Path(__file__).resolve().parents[3]
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


_mod = _import_script("triage_red_check")
main = _mod.main
build_parser = _mod.build_parser
triage = _mod.triage
evaluate_commit_rows = _mod.evaluate_commit_rows
normalize_row = _mod.normalize_row


# ---------------------------------------------------------------------------
# GraphQL response builders
# ---------------------------------------------------------------------------

_RUN_URL = "https://github.com/o/r/actions/runs/{run_id}/job/{job_id}"


def check_run(
    name: str,
    conclusion: str,
    *,
    status: str = "COMPLETED",
    run_id: int = 100,
    attempt: int = 1,
    job_id: int = 1,
    with_url: bool = True,
) -> dict:
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "detailsUrl": (
            _RUN_URL.format(run_id=run_id, job_id=job_id) if with_url else ""
        ),
        "checkSuite": {
            "workflowRun": {"databaseId": run_id, "runAttempt": attempt}
        },
    }


def status_context(name: str, state: str) -> dict:
    return {
        "__typename": "StatusContext",
        "context": name,
        "state": state,
        "targetUrl": f"https://ci.example/{name}",
    }


def commit_node(
    oid: str,
    nodes: list[dict] | None,
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> dict:
    rollup = None
    if nodes is not None:
        rollup = {
            "contexts": {
                "pageInfo": {
                    "hasNextPage": has_next_page,
                    "endCursor": end_cursor,
                },
                "nodes": nodes,
            }
        }
    return {
        "oid": oid,
        "committedDate": "2026-08-15T00:00:00Z",
        "statusCheckRollup": rollup,
    }


def history_response(commits: list[dict]) -> dict:
    return {
        "repository": {
            "ref": {
                "name": "main",
                "target": {"history": {"nodes": commits}},
            }
        }
    }


def _run_main(monkeypatch_graphql, argv: list[str] | None = None) -> tuple[int, dict]:
    """Drive main() with the API boundary mocked; return (exit_code, envelope)."""
    args = argv or ["--check-name", "Run Python Tests", "--output-format", "json"]
    with (
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(
            _mod, "resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")
        ),
        patch.object(_mod, "gh_graphql", side_effect=monkeypatch_graphql),
        patch("sys.stdout") as fake_stdout,
    ):
        rc = main(args)
    printed = "".join(
        call.args[0] for call in fake_stdout.write.call_args_list if call.args
    )
    envelope: dict = {}
    for line in printed.splitlines():
        line = line.strip()
        if line.startswith("{"):
            envelope = json.loads(line)
            break
    return rc, envelope


def _single_response(response: dict):
    def _dispatch(query: str, variables: dict) -> dict:
        assert "history" in query, "only the history query should be issued"
        return response
    return _dispatch


# ---------------------------------------------------------------------------
# Verdict: GREEN_ON_MAIN (exit 0)
# ---------------------------------------------------------------------------


class TestGreenOnMain:
    def test_success_on_head_commit_exits_zero(self):
        response = history_response(
            [commit_node("aaa", [check_run("Run Python Tests", "SUCCESS")])]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 0
        assert envelope["Data"]["Verdict"] == "GREEN_ON_MAIN"
        assert envelope["Data"]["EvidenceCommit"] == "aaa"

    def test_skipped_sibling_does_not_mask_success(self):
        # The rollup-collapse trap: one workflow emits SUCCESS and SKIPPED
        # rows for the same name in one run; SKIPPED must not win.
        response = history_response(
            [
                commit_node(
                    "aaa",
                    [
                        check_run("Run Python Tests", "SUCCESS", job_id=1),
                        check_run("Run Python Tests", "SKIPPED", job_id=2),
                    ],
                )
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 0
        assert envelope["Data"]["Verdict"] == "GREEN_ON_MAIN"

    def test_rerun_success_supersedes_first_attempt_failure(self):
        # Same run id, attempt 2 SUCCESS after attempt 1 FAILURE: latest
        # attempt decides, so main is green.
        response = history_response(
            [
                commit_node(
                    "aaa",
                    [
                        check_run("Run Python Tests", "FAILURE", attempt=1),
                        check_run("Run Python Tests", "SUCCESS", attempt=2),
                    ],
                )
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 0
        assert envelope["Data"]["Verdict"] == "GREEN_ON_MAIN"

    def test_walks_past_commit_without_the_check(self):
        # Path-filtered workflow did not run on head; older commit has the
        # completed run and supplies the verdict.
        response = history_response(
            [
                commit_node("head", [check_run("Other Check", "SUCCESS")]),
                commit_node("older", [check_run("Run Python Tests", "SUCCESS")]),
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 0
        assert envelope["Data"]["EvidenceCommit"] == "older"

    def test_pending_head_falls_back_to_older_completed_run(self):
        response = history_response(
            [
                commit_node(
                    "head",
                    [check_run("Run Python Tests", "", status="IN_PROGRESS")],
                ),
                commit_node("older", [check_run("Run Python Tests", "SUCCESS")]),
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 0
        assert envelope["Data"]["EvidenceCommit"] == "older"

    def test_cancelled_run_is_not_red_evidence(self):
        # Concurrency groups cancel superseded runs on main constantly; a
        # cancelled run proves nothing and the probe walks to older commits.
        response = history_response(
            [
                commit_node("head", [check_run("Run Python Tests", "CANCELLED")]),
                commit_node("older", [check_run("Run Python Tests", "SUCCESS")]),
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 0
        assert envelope["Data"]["EvidenceCommit"] == "older"

    def test_green_status_context_counts_as_evidence(self):
        response = history_response(
            [commit_node("aaa", [status_context("external/ci", "SUCCESS")])]
        )
        rc, envelope = _run_main(
            _single_response(response),
            ["--check-name", "external/ci", "--output-format", "json"],
        )
        assert rc == 0
        assert envelope["Data"]["Verdict"] == "GREEN_ON_MAIN"


# ---------------------------------------------------------------------------
# Verdict: RED_ON_MAIN (exit 1)
# ---------------------------------------------------------------------------


class TestRedOnMain:
    def test_failure_on_head_commit_exits_one_with_evidence_url(self):
        response = history_response(
            [commit_node("aaa", [check_run("Run Python Tests", "FAILURE", run_id=77)])]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 1
        data = envelope["Data"]
        assert data["Verdict"] == "RED_ON_MAIN"
        assert "/actions/runs/77/" in data["EvidenceUrl"]
        assert data["EvidenceCommit"] == "aaa"

    def test_colliding_name_red_in_second_workflow_wins(self):
        # Two workflows share the job name (distinct run ids). The green run
        # must not hide the red one; ambiguity is surfaced.
        response = history_response(
            [
                commit_node(
                    "aaa",
                    [
                        check_run("Validate budget", "SUCCESS", run_id=200),
                        check_run("Validate budget", "FAILURE", run_id=199),
                    ],
                )
            ]
        )
        rc, envelope = _run_main(
            _single_response(response),
            ["--check-name", "Validate budget", "--output-format", "json"],
        )
        assert rc == 1
        data = envelope["Data"]
        assert data["Verdict"] == "RED_ON_MAIN"
        assert "/actions/runs/199/" in data["EvidenceUrl"]
        assert data["AmbiguousDefinitions"] is True

    def test_red_status_context_counts_as_evidence(self):
        response = history_response(
            [commit_node("aaa", [status_context("external/ci", "FAILURE")])]
        )
        rc, envelope = _run_main(
            _single_response(response),
            ["--check-name", "external/ci", "--output-format", "json"],
        )
        assert rc == 1
        assert envelope["Data"]["Verdict"] == "RED_ON_MAIN"

    def test_missing_details_url_falls_back_to_run_url(self):
        # A check run can lack detailsUrl; the workflow run id still names the
        # evidence run, so the run URL is constructed instead of losing it.
        response = history_response(
            [
                commit_node(
                    "aaa",
                    [check_run("Run Python Tests", "FAILURE", run_id=88, with_url=False)],
                )
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 1
        assert (
            envelope["Data"]["EvidenceUrl"]
            == "https://github.com/o/r/actions/runs/88"
        )

    def test_red_sibling_wins_within_one_run(self):
        # Two jobs of one run share the name and both ran; the failure is
        # real and must win over the passing sibling (refs issue #4499).
        response = history_response(
            [
                commit_node(
                    "aaa",
                    [
                        check_run("Run Python Tests", "SUCCESS", job_id=1),
                        check_run("Run Python Tests", "FAILURE", job_id=2),
                    ],
                )
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 1
        assert envelope["Data"]["Verdict"] == "RED_ON_MAIN"


# ---------------------------------------------------------------------------
# Verdict: UNKNOWN (exit 3) - probe failure is not absence
# ---------------------------------------------------------------------------


class TestUnknown:
    def test_check_never_observed_exits_three_not_green(self):
        response = history_response(
            [
                commit_node("aaa", [check_run("Other Check", "SUCCESS")]),
                commit_node("bbb", [check_run("Other Check", "SUCCESS")]),
            ]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 3
        data = envelope["Data"]
        assert data["Verdict"] == "UNKNOWN"
        assert data["Reason"] == "not_observed_on_branch"
        assert data["Verdict"] != "GREEN_ON_MAIN"
        assert data["CommitsExamined"] == 2

    def test_empty_rollup_on_every_commit_is_unknown(self):
        response = history_response(
            [commit_node("aaa", None), commit_node("bbb", None)]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 3
        assert envelope["Data"]["Verdict"] == "UNKNOWN"

    def test_incomplete_pagination_is_unknown_even_with_green_row_visible(self):
        # A green row in the fetched page must not produce GREEN when later
        # pages never arrived: a red row for the same name could sit there.
        def dispatch(query: str, variables: dict) -> dict:
            if "history" in query:
                return history_response(
                    [
                        commit_node(
                            "aaa",
                            [check_run("Run Python Tests", "SUCCESS")],
                            has_next_page=True,
                            end_cursor="CUR1",
                        )
                    ]
                )
            # Context page fetch returns a malformed page (no pageInfo), so
            # pagination reports incomplete.
            return {"repository": {"object": {"statusCheckRollup": None}}}

        rc, envelope = _run_main(dispatch)
        assert rc == 3
        data = envelope["Data"]
        assert data["Verdict"] == "UNKNOWN"
        assert data["Reason"] == "contexts_incomplete"

    def test_api_error_exits_three_and_names_unknown(self):
        def dispatch(query: str, variables: dict) -> dict:
            raise RuntimeError("GraphQL request failed: HTTP 502")

        rc, envelope = _run_main(dispatch)
        assert rc == 3
        assert envelope.get("Success") is False
        assert "UNKNOWN" in str(envelope.get("Error"))

    def test_malformed_history_payload_exits_three_not_traceback(self):
        # ADR-035 reserves exit 1 for the RED_ON_MAIN verdict, so a malformed
        # payload must map to ApiError (exit 3), never an AttributeError.
        response = {"repository": {"ref": {"name": "main", "target": {"history": "junk"}}}}
        rc, envelope = _run_main(_single_response(response))
        assert rc == 3
        assert envelope.get("Success") is False

    def test_non_object_history_node_exits_three(self):
        response = {
            "repository": {
                "ref": {"name": "main", "target": {"history": {"nodes": ["junk"]}}}
            }
        }
        rc, envelope = _run_main(_single_response(response))
        assert rc == 3
        assert envelope.get("Success") is False

    def test_non_object_rollup_exits_three(self):
        commit = {
            "oid": "aaa",
            "committedDate": "2026-08-15T00:00:00Z",
            "statusCheckRollup": "junk",
        }
        rc, envelope = _run_main(_single_response(history_response([commit])))
        assert rc == 3
        assert envelope.get("Success") is False

    def test_non_object_contexts_exits_three(self):
        commit = {
            "oid": "aaa",
            "committedDate": "2026-08-15T00:00:00Z",
            "statusCheckRollup": {"contexts": ["junk"]},
        }
        rc, envelope = _run_main(_single_response(history_response([commit])))
        assert rc == 3
        assert envelope.get("Success") is False

    def test_stale_only_rows_are_unknown(self):
        response = history_response(
            [commit_node("aaa", [check_run("Run Python Tests", "STALE")])]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 3
        assert envelope["Data"]["Verdict"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Config and auth failure paths
# ---------------------------------------------------------------------------


class TestFailurePaths:
    def test_branch_not_found_exits_two(self):
        response = {"repository": {"ref": None}}
        rc, envelope = _run_main(
            _single_response(response),
            ["--check-name", "X", "--branch", "nope", "--output-format", "json"],
        )
        assert rc == 2
        assert envelope.get("Success") is False

    def test_history_depth_out_of_range_exits_two(self):
        rc, _ = _run_main(
            _single_response({}),
            ["--check-name", "X", "--history-depth", "0", "--output-format", "json"],
        )
        assert rc == 2
        rc, _ = _run_main(
            _single_response({}),
            ["--check-name", "X", "--history-depth", "51", "--output-format", "json"],
        )
        assert rc == 2

    def test_missing_check_name_is_usage_error(self):
        with pytest.raises(SystemExit) as excinfo:
            build_parser().parse_args([])
        assert excinfo.value.code == 2

    def test_auth_failure_propagates(self):
        with (
            patch.object(
                _mod, "assert_gh_authenticated", side_effect=SystemExit(4)
            ),
            pytest.raises(SystemExit) as excinfo,
        ):
            main(["--check-name", "X", "--output-format", "json"])
        assert excinfo.value.code == 4


# ---------------------------------------------------------------------------
# Unit-level edge coverage
# ---------------------------------------------------------------------------


class TestEvaluateCommitRows:
    def test_no_rows_yields_no_verdict(self):
        verdict, evidence, ambiguous = evaluate_commit_rows([])
        assert verdict is None
        assert evidence is None
        assert ambiguous is False

    def test_two_green_runs_are_green_and_ambiguous(self):
        rows = [
            normalize_row(check_run("N", "SUCCESS", run_id=1)),
            normalize_row(check_run("N", "SUCCESS", run_id=2)),
        ]
        verdict, _, ambiguous = evaluate_commit_rows(rows)
        assert verdict == "green"
        assert ambiguous is True

    def test_unrecognized_node_type_normalizes_to_none(self):
        assert normalize_row({"__typename": "SomethingElse"}) is None

    def test_non_dict_context_node_is_dropped_not_raised(self):
        assert normalize_row("junk") is None

    def test_garbage_node_beside_valid_success_still_green(self):
        response = history_response(
            [commit_node("aaa", ["junk", check_run("Run Python Tests", "SUCCESS")])]
        )
        rc, envelope = _run_main(_single_response(response))
        assert rc == 0
        assert envelope["Data"]["Verdict"] == "GREEN_ON_MAIN"


class TestTriageOutputShape:
    def test_matched_rows_reported_for_evidence_commit(self):
        commits = [
            {
                "Oid": "aaa",
                "CommittedDate": "2026-08-15T00:00:00Z",
                "ContextNodes": [
                    check_run("N", "FAILURE"),
                    check_run("Other", "SUCCESS"),
                ],
                "PagesComplete": True,
            }
        ]
        result = triage(commits, "N")
        assert result["Verdict"] == "RED_ON_MAIN"
        assert len(result["MatchedRows"]) == 1
        assert result["MatchedRows"][0]["Name"] == "N"

    def test_pull_request_context_is_echoed(self):
        response = history_response(
            [commit_node("aaa", [check_run("Run Python Tests", "SUCCESS")])]
        )
        rc, envelope = _run_main(
            _single_response(response),
            [
                "--check-name", "Run Python Tests",
                "--pull-request", "123",
                "--output-format", "json",
            ],
        )
        assert rc == 0
        assert envelope["Data"]["PullRequest"] == 123
