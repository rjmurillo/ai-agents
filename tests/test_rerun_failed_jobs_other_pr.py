"""Tests for rerun_failed_jobs.py: runs that share a commit with another PR."""

from __future__ import annotations

import pytest

from tests.rerun_failed_jobs_harness import (
    envelope,
    pr_fake,
    rerun_ok,
    run_main,
    run_obj,
    runs_page,
)


class TestOtherPrRuns:
    """Two branches can share a commit, so a run's head SHA does not name its PR."""

    def test_run_that_belongs_to_another_pr_does_not_hide_this_prs_failure(self, capsys):
        mine = {
            **run_obj(100),
            "workflow_id": 50,
            "run_number": 3,
            "pull_requests": [{"number": 7}],
        }
        theirs = {
            **run_obj(101, conclusion="success"),
            "workflow_id": 50,
            "run_number": 4,
            "pull_requests": [{"number": 8}],
        }
        client = pr_fake([runs_page([mine, theirs])], rerun_ok(100))
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert [r["run_id"] for r in env["Data"]["reruns"]] == [100]
        assert env["Data"]["skipped_other_pr_run_ids"] == [101]

    def test_failed_run_of_another_pr_is_not_rerun(self, capsys):
        theirs = {**run_obj(101), "pull_requests": [{"number": 8}]}
        client = pr_fake([runs_page([theirs])])
        rc = run_main(["--pull-request", "7"], client)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["reason"] == "no_failed_runs"
        assert env["Data"]["skipped_other_pr_run_ids"] == [101]
        assert client.post_calls == []

    def test_run_shared_by_two_prs_is_kept(self, capsys):
        shared = {**run_obj(100), "pull_requests": [{"number": 8}, {"number": 7}]}
        client = pr_fake([runs_page([shared])], rerun_ok(100))
        assert run_main(["--pull-request", "7"], client) == 0
        assert len(client.post_calls) == 1

    @pytest.mark.parametrize("linked", [[], None])
    def test_run_with_no_pr_link_is_kept(self, linked, capsys):
        """A fork PR run lists no pull_requests, so SHA is the only evidence."""
        unlinked = {**run_obj(100), "pull_requests": linked}
        client = pr_fake([runs_page([unlinked])], rerun_ok(100))
        assert run_main(["--pull-request", "7"], client) == 0
        assert len(client.post_calls) == 1

    def test_malformed_pull_request_entries_do_not_crash(self, capsys):
        odd = {**run_obj(100), "pull_requests": ["x", {"number": 7}]}
        client = pr_fake([runs_page([odd])], rerun_ok(100))
        assert run_main(["--pull-request", "7"], client) == 0
