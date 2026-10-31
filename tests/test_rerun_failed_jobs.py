"""Tests for rerun_failed_jobs.py: classify, page, dedupe, and rerun failed runs."""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.rerun_failed_jobs_harness import (
    CANNOT_RETRY,
    HEAD,
    JOB_77,
    PR_ENDPOINT,
    FakeClient,
    GhAuthResult,
    GhAuthStatus,
    envelope,
    pr_fake,
    rerun_ok,
    run_main,
    run_obj,
    runs_page,
    script,
)


class TestPullRequestRerun:
    def test_reruns_each_failed_run_for_head_sha(self, capsys):
        """Positive: two failed runs and one success; only the failed two rerun."""
        runs = [run_obj(1), run_obj(2, conclusion="success"), run_obj(3, conclusion="timed_out")]
        client = pr_fake([runs_page(runs)], {**rerun_ok(1), **rerun_ok(3)})
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Success"] is True
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1, 3]
        assert env["Data"]["reason"] == "rerun_requested"
        assert env["Data"]["head_sha"] == HEAD
        assert [call[0] for call in client.post_calls] == [
            "repos/o/r/actions/runs/1/rerun-failed-jobs",
            "repos/o/r/actions/runs/3/rerun-failed-jobs",
        ]

    def test_no_failed_runs_exits_zero_without_post(self, capsys):
        client = pr_fake([runs_page([run_obj(1, conclusion="success")])])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reason"] == "no_failed_runs"
        assert env["Data"]["reruns"] == []
        assert client.post_calls == []

    def test_empty_run_list_is_no_failed_runs(self, capsys):
        client = pr_fake([runs_page([])])
        assert run_main(["--pull-request", "7"], client) == 0
        assert envelope(capsys)["Data"]["reason"] == "no_failed_runs"

    def test_only_in_progress_runs_exit_one(self, capsys):
        runs = [run_obj(5, status="in_progress", conclusion=None)]
        client = pr_fake([runs_page(runs)])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 1
        assert env["Data"]["reason"] == "run_in_progress"
        assert env["Data"]["in_progress_runs"][0]["run_id"] == 5
        assert client.post_calls == []

    def test_mixed_failed_and_in_progress_reports_skipped(self, capsys):
        runs = [run_obj(1), run_obj(5, status="queued", conclusion=None)]
        client = pr_fake([runs_page(runs)], rerun_ok(1))
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1]
        assert [r["run_id"] for r in env["Data"]["skipped_in_progress"]] == [5]
        assert [r["status"] for r in env["Data"]["skipped_in_progress"]] == ["queued"]

    def test_duplicate_run_ids_across_pages_post_once(self, capsys):
        full = [run_obj(100 + i, conclusion="success") for i in range(99)] + [run_obj(1)]
        page2 = [run_obj(1), run_obj(2)]
        client = pr_fake([runs_page(full, total=101), runs_page(page2, total=101)])
        client.posts.update(rerun_ok(1))
        client.posts.update(rerun_ok(2))
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1, 2]
        assert len(client.post_calls) == 2

    def test_unknown_pr_exits_two(self, capsys):
        client = FakeClient({PR_ENDPOINT: RuntimeError("gh api GET failed: Not Found (HTTP 404)")})
        assert run_main(["--pull-request", "7"], client) == 2
        assert envelope(capsys)["Error"]["Type"] == "NotFound"

    def test_pr_without_head_sha_exits_three(self, capsys):
        client = FakeClient({PR_ENDPOINT: {"state": "open", "head": {}}})
        assert run_main(["--pull-request", "7"], client) == 3


class TestRefusal:
    def test_cannot_be_retried_exits_100_with_fallbacks_and_no_retry(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(9)])],
            {"repos/o/r/actions/runs/9/rerun-failed-jobs": RuntimeError(CANNOT_RETRY.format(id=9))},
        )
        rc = run_main(["--pull-request", "7"], client)
        captured = capsys.readouterr()
        env = json.loads(captured.out.strip().splitlines()[-1])
        assert rc == 100
        assert env["Error"]["Code"] == 100
        assert env["Data"]["reason"] == "cannot_be_retried"
        assert env["Data"]["refused"][0]["run_id"] == 9
        assert len(client.post_calls) == 1, "authoritative refusal must not be retried"
        fallbacks = " ".join(env["Data"]["fallbacks"])
        assert "base branch" in fallbacks
        assert "empty commit" in fallbacks
        assert "human" in fallbacks
        assert "[FALLBACK]" in captured.err

    @pytest.mark.parametrize(
        "text",
        [
            "run 40713397099 cannot be rerun; This workflow run cannot be retried",
            "gh: Cannot be RETRIED (HTTP 403)",
            "This workflow run cannot be re-run",
        ],
    )
    def test_refusal_markers(self, text):
        assert script.is_cannot_retry_refusal(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "HTTP 502 Bad Gateway",
            "Resource not accessible by integration",
            "Not Found (HTTP 404)",
        ],
    )
    def test_non_refusal_text_is_not_classified(self, text):
        assert script.is_cannot_retry_refusal(text) is False

    def test_refusal_on_one_run_still_reruns_the_others(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1), run_obj(2)])],
            {
                "repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(
                    CANNOT_RETRY.format(id=1)
                ),
                **rerun_ok(2),
            },
        )
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 100
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [2]
        assert [r["run_id"] for r in env["Data"]["refused"]] == [1]

    def test_other_api_error_exits_three(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1)])],
            {"repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError("failed: HTTP 500")},
        )
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"

    def test_post_timeout_exits_three_outcome_unknown(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1)])],
            {"repos/o/r/actions/runs/1/rerun-failed-jobs": subprocess.TimeoutExpired("gh", 30)},
        )
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "Timeout"
        assert "unknown" in env["Error"]["Message"]


class TestAuth:
    def test_preflight_auth_failure_exits_four_without_api_calls(self, capsys):
        client = pr_fake([])
        auth = GhAuthResult(GhAuthStatus.INVALID_CREDENTIALS, "bad token")
        assert run_main(["--pull-request", "7"], client, auth=auth) == 4
        assert client.get_calls == []

    def test_graphql_blocked_session_still_runs_over_rest(self, capsys):
        """The script reaches GitHub only through REST, so a GraphQL block is not fatal."""
        client = pr_fake([runs_page([run_obj(1)])], rerun_ok(1))
        auth = GhAuthResult(GhAuthStatus.GRAPHQL_BLOCKED, "graphql refused")
        assert run_main(["--pull-request", "7"], client, auth=auth) == 0
        assert len(client.post_calls) == 1

    @pytest.mark.parametrize(
        "status",
        [GhAuthStatus.INVALID_CREDENTIALS, GhAuthStatus.MISSING_GH],
    )
    def test_other_auth_statuses_still_exit_four(self, status, capsys):
        client = pr_fake([])
        assert run_main(["--pull-request", "7"], client, auth=GhAuthResult(status, "x")) == 4
        assert client.get_calls == []

    def test_post_auth_error_exits_four(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1)])],
            {
                "repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(
                    "Resource not accessible by integration (HTTP 403)"
                )
            },
        )
        assert run_main(["--pull-request", "7"], client) == 4
        assert envelope(capsys)["Error"]["Type"] == "AuthError"

    def test_pr_lookup_auth_error_exits_four(self, capsys):
        client = FakeClient({PR_ENDPOINT: RuntimeError("Bad credentials (HTTP 401)")})
        assert run_main(["--pull-request", "7"], client) == 4


class TestRunId:
    def test_reruns_completed_failed_run(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42)}, rerun_ok(42))
        rc = run_main(["--run-id", "42"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reruns"][0]["run_id"] == 42
        assert env["Data"]["reruns"][0]["action"] == "rerun_failed_jobs"

    def test_in_progress_run_exits_one_and_reports_status(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42, "in_progress", None)})
        rc = run_main(["--run-id", "42"], client)
        env = envelope(capsys)
        assert rc == 1
        assert env["Data"]["reason"] == "run_in_progress"
        assert env["Data"]["run_status"] == "in_progress"
        assert client.post_calls == []

    def test_successful_run_is_no_failed_runs(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42, conclusion="success")})
        assert run_main(["--run-id", "42"], client) == 0
        assert envelope(capsys)["Data"]["reason"] == "no_failed_runs"
        assert client.post_calls == []

    def test_missing_run_exits_two(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": RuntimeError("Not Found (HTTP 404)")})
        assert run_main(["--run-id", "42"], client) == 2

    def test_run_refusal_exits_100(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42)},
            {
                "repos/o/r/actions/runs/42/rerun-failed-jobs": RuntimeError(
                    CANNOT_RETRY.format(id=42)
                )
            },
        )
        assert run_main(["--run-id", "42"], client) == 100

    def test_job_id_reruns_one_job(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42), JOB_77: {"id": 77, "run_id": 42}},
            {"repos/o/r/actions/jobs/77/rerun": {}},
        )
        rc = run_main(["--run-id", "42", "--job-id", "77"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reruns"][0]["job_id"] == 77
        assert env["Data"]["reruns"][0]["action"] == "rerun_job"
        assert [c[0] for c in client.post_calls] == ["repos/o/r/actions/jobs/77/rerun"]

    def test_job_rerun_on_in_progress_run_exits_one(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42, "queued", None), JOB_77: {"run_id": 42}}
        )
        assert run_main(["--run-id", "42", "--job-id", "77"], client) == 1
        assert client.post_calls == []
