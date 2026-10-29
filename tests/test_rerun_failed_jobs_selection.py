"""Tests for rerun_failed_jobs.py: batch outcomes, selection, job mode, and arguments."""

from __future__ import annotations

import json

import pytest

from tests.rerun_failed_jobs_harness import (
    CANNOT_RETRY,
    JOB_77,
    PR_ENDPOINT,
    SKILL_MD,
    FakeClient,
    envelope,
    pr_fake,
    rerun_ok,
    run_main,
    run_obj,
    runs_page,
    script,
)


class TestBatchOutcomes:
    def test_failure_on_second_run_still_reports_first_and_attempts_third(self, capsys):
        runs = [run_obj(1), run_obj(2), run_obj(3)]
        client = pr_fake(
            [runs_page(runs)],
            {
                **rerun_ok(1),
                "repos/o/r/actions/runs/2/rerun-failed-jobs": RuntimeError("failed: HTTP 500"),
                **rerun_ok(3),
            },
        )
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 3
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1, 3]
        assert [r["run_id"] for r in env["Data"]["failed"]] == [2]
        assert len(client.post_calls) == 3

    def test_auth_fault_stops_batch_and_names_unattempted_runs(self, capsys):
        runs = [run_obj(1), run_obj(2), run_obj(3)]
        client = pr_fake(
            [runs_page(runs)],
            {
                **rerun_ok(1),
                "repos/o/r/actions/runs/2/rerun-failed-jobs": RuntimeError(
                    "Resource not accessible by integration (HTTP 403)"
                ),
            },
        )
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 4
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [1]
        assert [r["run_id"] for r in env["Data"]["failed"]] == [2]
        assert env["Data"]["failed"][0]["stopped_batch"] is True
        assert env["Data"]["not_attempted_run_ids"] == [3]
        assert len(client.post_calls) == 2

    def test_refused_entry_keeps_github_wording(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(9)])],
            {"repos/o/r/actions/runs/9/rerun-failed-jobs": RuntimeError(CANNOT_RETRY.format(id=9))},
        )
        run_main(["--pull-request", "7"], client)
        detail = envelope(capsys)["Data"]["refused"][0]["detail"]
        assert "cannot be retried" in detail

    def test_failure_and_refusal_together_exit_three_with_fallbacks(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1), run_obj(2)])],
            {
                "repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(
                    CANNOT_RETRY.format(id=1)
                ),
                "repos/o/r/actions/runs/2/rerun-failed-jobs": RuntimeError("failed: HTTP 500"),
            },
        )
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 3
        assert env["Data"]["fallbacks"]


class TestRunSelection:
    def test_cancelled_run_is_skipped_in_pr_mode(self, capsys):
        runs = [run_obj(1, conclusion="cancelled")]
        client = pr_fake([runs_page(runs)])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reason"] == "no_failed_runs"
        assert [r["run_id"] for r in env["Data"]["skipped_cancelled"]] == [1]
        assert client.post_calls == []

    def test_cancelled_run_is_rerun_when_named_by_run_id(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42, conclusion="cancelled")}, rerun_ok(42)
        )
        assert run_main(["--run-id", "42"], client) == 0
        assert len(client.post_calls) == 1

    def test_superseded_failed_run_is_not_rerun(self, capsys):
        """An older failed run of the same workflow and event loses to the newer run."""
        old = {**run_obj(1), "workflow_id": 50, "run_number": 3}
        new = {**run_obj(2, conclusion="success"), "workflow_id": 50, "run_number": 4}
        client = pr_fake([runs_page([old, new])])
        rc = run_main(["--pull-request", "7"], client)
        assert rc == 0
        assert envelope(capsys)["Data"]["reason"] == "no_failed_runs"
        assert client.post_calls == []

    def test_newest_failed_run_of_a_workflow_is_rerun(self, capsys):
        old = {**run_obj(1), "workflow_id": 50, "run_number": 3}
        new = {**run_obj(2), "workflow_id": 50, "run_number": 4}
        client = pr_fake([runs_page([old, new])], rerun_ok(2))
        assert run_main(["--pull-request", "7"], client) == 0
        assert [c[0] for c in client.post_calls] == ["repos/o/r/actions/runs/2/rerun-failed-jobs"]

    @pytest.mark.parametrize("state", ["closed", None])
    def test_pr_that_is_not_open_exits_one(self, state, capsys):
        client = pr_fake([], state=state)
        rc = run_main(["--pull-request", "7"], client)
        assert rc == 1
        assert envelope(capsys)["Data"]["reason"] == "pr_not_open"
        assert client.post_calls == []

    def test_pr_response_that_is_not_an_object_exits_three(self, capsys):
        client = FakeClient({PR_ENDPOINT: []})
        assert run_main(["--pull-request", "7"], client) == 3

    def test_malformed_run_items_are_named_in_the_gap_message(self, capsys):
        page = [{"name": "no id"}, run_obj(1, conclusion="success")]
        client = pr_fake([runs_page(page, total=5)])
        assert run_main(["--pull-request", "7"], client) == 3
        assert "1 malformed" in envelope(capsys)["Error"]["Message"]


class TestJobMode:
    def test_job_from_another_run_exits_one_without_post(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42), JOB_77: {"id": 77, "run_id": 99}}
        )
        rc = run_main(["--run-id", "42", "--job-id", "77"], client)
        env = envelope(capsys)
        assert rc == 1
        assert env["Data"]["reason"] == "job_run_mismatch"
        assert env["Data"]["job_run_id"] == 99
        assert client.post_calls == []

    def test_unknown_job_exits_two(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42), JOB_77: RuntimeError("Not Found (HTTP 404)")}
        )
        assert run_main(["--run-id", "42", "--job-id", "77"], client) == 2

    def test_job_refusal_exits_100(self, capsys):
        client = FakeClient(
            {"repos/o/r/actions/runs/42": run_obj(42), JOB_77: {"run_id": 42}},
            {"repos/o/r/actions/jobs/77/rerun": RuntimeError(CANNOT_RETRY.format(id=77))},
        )
        rc = run_main(["--run-id", "42", "--job-id", "77"], client)
        assert rc == 100
        assert envelope(capsys)["Data"]["refused"][0]["job_id"] == 77


class TestEdgeCases:
    def test_rate_limit_text_exits_three_with_rate_limit_type(self, capsys):
        client = pr_fake([RuntimeError("API rate limit exceeded (HTTP 403)")])
        assert run_main(["--pull-request", "7"], client) == 3
        env = envelope(capsys)
        assert env["Error"]["Type"] == "RateLimitError"
        assert env["Data"]["reason"] == "rate_limited"

    def test_run_response_that_is_not_a_run_exits_three(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": {"message": "odd"}})
        assert run_main(["--run-id", "42"], client) == 3

    def test_non_numeric_id_exits_one(self, capsys):
        assert run_main(["--run-id", "abc"], FakeClient({})) == 1


class TestArguments:
    def test_requires_pull_request_or_run_id(self, capsys):
        assert run_main([], FakeClient({})) == 1

    def test_rejects_both_pull_request_and_run_id(self, capsys):
        assert run_main(["--pull-request", "7", "--run-id", "42"], FakeClient({})) == 1

    def test_job_id_requires_run_id(self, capsys):
        assert run_main(["--pull-request", "7", "--job-id", "77"], FakeClient({})) == 1
        assert envelope(capsys)["Error"]["Type"] == "InvalidParams"

    @pytest.mark.parametrize("flag", ["--pull-request", "--run-id"])
    def test_rejects_non_positive_ids(self, flag, capsys):
        assert run_main([flag, "0"], FakeClient({})) == 1


class TestDocumentation:
    def test_script_is_listed_in_skill_md(self):
        assert "rerun_failed_jobs.py" in SKILL_MD.read_text(encoding="utf-8")


class TestPagination:
    def test_second_page_runs_are_included(self, capsys):
        page1 = [run_obj(100 + i, conclusion="success") for i in range(100)]
        page2 = [run_obj(1)]
        client = pr_fake([runs_page(page1, total=101), runs_page(page2, total=101)], rerun_ok(1))
        rc = run_main(["--pull-request", "7"], client)
        assert rc == 0
        assert [r["run_id"] for r in envelope(capsys)["Data"]["reruns"]] == [1]
        assert client.get_calls[-1].endswith("page=2")

    def test_short_final_page_with_missing_runs_fails_loud(self, capsys):
        """total_count says 150 but the walk ends with 100: a gap, never a partial."""
        page1 = [run_obj(100 + i, conclusion="success") for i in range(100)]
        client = pr_fake([runs_page(page1, total=150), runs_page([], total=150)])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 3
        assert env["Data"]["reason"] == "pagination_incomplete"
        assert client.post_calls == []

    def test_page_cap_fails_loud(self, capsys):
        pages = []
        for n in range(script._MAX_PAGES):
            pages.append(
                runs_page(
                    [run_obj(n * 100 + i + 1, conclusion="success") for i in range(100)],
                    total=10**6,
                )
            )
        client = pr_fake(pages)
        rc = run_main(["--pull-request", "7"], client)
        assert rc == 3
        assert envelope(capsys)["Data"]["reason"] == "pagination_incomplete"

    def test_non_object_page_fails_loud(self, capsys):
        client = pr_fake([[run_obj(1)]])
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Data"]["reason"] == "pagination_incomplete"

    def test_missing_total_count_fails_loud(self, capsys):
        client = pr_fake([{"workflow_runs": [run_obj(1)]}])
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Data"]["reason"] == "pagination_incomplete"

    def test_list_fetch_error_exits_three(self, capsys):
        client = pr_fake([RuntimeError("gh api GET failed: HTTP 502")])
        assert run_main(["--pull-request", "7"], client) == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"


class TestEnvelopeContract:
    BATCH_KEYS = {
        "reruns",
        "refused",
        "failed",
        "not_attempted_run_ids",
        "skipped_in_progress",
        "skipped_cancelled",
    }

    def test_success_envelope_carries_every_batch_key(self, capsys):
        client = pr_fake([runs_page([run_obj(1)])], rerun_ok(1))
        run_main(["--pull-request", "7"], client)
        assert self.BATCH_KEYS <= set(envelope(capsys)["Data"])

    def test_refusal_envelope_keeps_in_progress_runs(self, capsys):
        runs = [run_obj(1), run_obj(5, status="queued", conclusion=None)]
        client = pr_fake(
            [runs_page(runs)],
            {"repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(CANNOT_RETRY.format(id=1))},
        )
        run_main(["--pull-request", "7"], client)
        data = envelope(capsys)["Data"]
        assert self.BATCH_KEYS <= set(data)
        assert [r["run_id"] for r in data["skipped_in_progress"]] == [5]

    def test_auth_stop_envelope_carries_every_batch_key(self, capsys):
        client = pr_fake(
            [runs_page([run_obj(1)])],
            {
                "repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(
                    "Bad credentials (HTTP 401)"
                )
            },
        )
        run_main(["--pull-request", "7"], client)
        assert self.BATCH_KEYS <= set(envelope(capsys)["Data"])

    def test_job_response_without_run_id_is_an_api_error(self, capsys):
        client = FakeClient({"repos/o/r/actions/runs/42": run_obj(42), JOB_77: {"id": 77}})
        assert run_main(["--run-id", "42", "--job-id", "77"], client) == 3

    def test_non_integer_run_number_does_not_crash_selection(self, capsys):
        odd = {**run_obj(1), "run_number": "x"}
        client = pr_fake([runs_page([odd])], rerun_ok(1))
        assert run_main(["--pull-request", "7"], client) == 0


class TestStopAfterRefusal:
    @pytest.mark.parametrize(
        ("text", "code"),
        [("Bad credentials (HTTP 401)", 4), ("API rate limit exceeded (HTTP 403)", 3)],
    )
    def test_fallbacks_survive_a_stop_that_follows_a_refusal(self, text, code, capsys):
        client = pr_fake(
            [runs_page([run_obj(1), run_obj(2)])],
            {
                "repos/o/r/actions/runs/1/rerun-failed-jobs": RuntimeError(
                    CANNOT_RETRY.format(id=1)
                ),
                "repos/o/r/actions/runs/2/rerun-failed-jobs": RuntimeError(text),
            },
        )
        rc = run_main(["--pull-request", "7"], client)
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip().splitlines()[-1])["Data"]
        assert rc == code
        assert [r["run_id"] for r in data["refused"]] == [1]
        assert data["fallbacks"]
        assert "[FALLBACK]" in captured.err
