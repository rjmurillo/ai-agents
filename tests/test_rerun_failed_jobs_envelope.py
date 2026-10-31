"""Tests for rerun_failed_jobs.py: the Data envelope contract on every rerun exit."""

from __future__ import annotations

import json

import pytest

from tests.rerun_failed_jobs_harness import (
    CANNOT_RETRY,
    JOB_77,
    FakeClient,
    envelope,
    pr_fake,
    rerun_ok,
    run_main,
    run_obj,
    runs_page,
)


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
