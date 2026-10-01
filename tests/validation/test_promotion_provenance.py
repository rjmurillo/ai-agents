"""Run provenance and check-run corroboration, ADR-113 decisions 2 and 5.

Every branch is driven with a plain dict, the shape the REST API returns, so a
test reads as the payload it stands for.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.validation.evidence import CheckOutcome, EvidenceState
from scripts.validation.promotion_evidence import EvidenceRecord, parse_evidence
from scripts.validation.promotion_provenance import (
    ACTIONS_APP_ID,
    Corroboration,
    combine,
    corroborate,
    run_problem,
)

SHA = "a" * 40
WORKFLOW = ".github/workflows/pytest.yml"
REPO = "owner/repo"
RUN_ID = 900
JOB_ID = 5001


def _run(**overrides: Any) -> dict[str, Any]:
    run: dict[str, Any] = {
        "id": RUN_ID,
        "status": "completed",
        "head_sha": SHA,
        "event": "push",
        "path": WORKFLOW,
        "head_branch": "main",
        "repository": {"id": 7},
        "head_repository": {"id": 7},
    }
    run.update(overrides)
    return run


def _problem(**overrides: Any) -> str | None:
    return run_problem(
        _run(**overrides), candidate_sha=SHA, workflow=WORKFLOW, default_branch="main"
    )


class TestRunProblem:
    def test_a_default_branch_push_run_passes(self) -> None:
        assert _problem() is None

    def test_a_merge_queue_run_for_the_default_branch_passes(self) -> None:
        assert _problem(event="merge_group", head_branch="gh-readonly-queue/main/pr-1-abc") is None

    @pytest.mark.parametrize(
        "branch",
        [
            "gh-readonly-queue/other/pr-1-abc",
            "gh-readonly-queue/main",
            "gh-readonly-queue/mainline/pr-1",
            "gh-readonly-queue/",
        ],
    )
    def test_a_merge_queue_run_for_another_base_is_refused(self, branch: str) -> None:
        assert _problem(event="merge_group", head_branch=branch) == "run.ref_mismatch"

    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            ({"status": "in_progress"}, "run.incomplete"),
            ({"status": None}, "run.incomplete"),
            ({"head_sha": "b" * 40}, "run.sha_mismatch"),
            ({"head_sha": None}, "run.sha_mismatch"),
            ({"event": "pull_request"}, "run.event_not_promotable"),
            ({"event": "workflow_dispatch"}, "run.event_not_promotable"),
            ({"event": "schedule"}, "run.event_not_promotable"),
            ({"event": None}, "run.event_not_promotable"),
            ({"path": ".github/workflows/other.yml"}, "run.workflow_mismatch"),
            ({"path": WORKFLOW + "@refs/heads/x"}, "run.workflow_mismatch"),
            ({"head_branch": "feature"}, "run.ref_mismatch"),
            ({"head_branch": ""}, "run.ref_mismatch"),
            ({"head_branch": None}, "run.ref_mismatch"),
            ({"head_branch": 5}, "run.ref_mismatch"),
            ({"event": "merge_group", "head_branch": "main"}, "run.ref_mismatch"),
            ({"head_repository": {"id": 8}}, "run.repository_mismatch"),
            ({"head_repository": None}, "run.repository_mismatch"),
            ({"repository": {}}, "run.repository_mismatch"),
            (
                {"head_repository": {"id": True}, "repository": {"id": True}},
                "run.repository_mismatch",
            ),
        ],
    )
    def test_each_mismatch_names_its_reason(self, overrides: dict[str, Any], reason: str) -> None:
        assert _problem(**overrides) == reason

    def test_a_push_with_no_default_branch_name_is_refused(self) -> None:
        got = run_problem(_run(), candidate_sha=SHA, workflow=WORKFLOW, default_branch="")
        assert got == "run.ref_mismatch"

    def test_an_empty_payload_is_refused(self) -> None:
        got = run_problem({}, candidate_sha=SHA, workflow=WORKFLOW, default_branch="main")
        assert got == "run.incomplete"


def _job(**overrides: Any) -> dict[str, Any]:
    job: dict[str, Any] = {"id": JOB_ID, "name": "Run Python Tests", "run_id": RUN_ID}
    job.update(overrides)
    return job


def _check(job_id: int = JOB_ID, **overrides: Any) -> dict[str, Any]:
    check: dict[str, Any] = {
        "id": job_id,
        "name": "Run Python Tests",
        "status": "completed",
        "conclusion": "success",
        "app": {"id": ACTIONS_APP_ID},
        "details_url": f"https://github.com/{REPO}/actions/runs/{RUN_ID}/job/{job_id}",
    }
    check.update(overrides)
    return check


def _corroborate(
    jobs: list[dict[str, Any]] | None = None,
    checks: dict[int, dict[str, Any]] | None = None,
    repository: str = REPO,
) -> Corroboration:
    return corroborate(
        job_name="Run Python Tests",
        run_id=RUN_ID,
        repository=repository,
        latest_jobs=[_job()] if jobs is None else jobs,
        check_runs={JOB_ID: _check()} if checks is None else checks,
    )


class TestCorroborate:
    def test_a_successful_check_run_corroborates(self) -> None:
        assert _corroborate() == Corroboration(EvidenceState.PASS)

    @pytest.mark.parametrize(
        "conclusion", ["failure", "timed_out", "action_required", "startup_failure"]
    )
    def test_a_failing_conclusion_reads_fail(self, conclusion: str) -> None:
        got = _corroborate(checks={JOB_ID: _check(conclusion=conclusion)})
        assert (got.state, got.reason) == (EvidenceState.FAIL, f"checkrun.{conclusion}")

    @pytest.mark.parametrize("conclusion", ["neutral", "skipped", "cancelled", "stale"])
    def test_a_non_success_conclusion_reads_unknown(self, conclusion: str) -> None:
        got = _corroborate(checks={JOB_ID: _check(conclusion=conclusion)})
        assert (got.state, got.reason) == (EvidenceState.UNKNOWN, f"checkrun.{conclusion}")

    @pytest.mark.parametrize("conclusion", [None, "", "Success", "a.b", 5, "x" * 31, "new_value!"])
    def test_an_unlisted_conclusion_reads_unknown_with_a_safe_reason(self, conclusion: Any) -> None:
        got = _corroborate(checks={JOB_ID: _check(conclusion=conclusion)})
        assert got.state is EvidenceState.UNKNOWN
        assert got.reason == "checkrun.unrecognized"

    @pytest.mark.parametrize("status", ["in_progress", "queued", None])
    def test_a_job_that_has_not_completed_reads_unknown(self, status: Any) -> None:
        got = _corroborate(checks={JOB_ID: _check(status=status)})
        assert (got.state, got.reason) == (EvidenceState.UNKNOWN, "checkrun.not_completed")

    def test_no_current_job_reads_unknown(self) -> None:
        got = _corroborate(jobs=[])
        assert (got.state, got.reason) == (EvidenceState.UNKNOWN, "checkrun.absent")

    @pytest.mark.parametrize(
        "job",
        [
            _job(name="Other"),
            _job(run_id=1),
            _job(id="5001"),
            _job(id=True),
            {"name": "Run Python Tests"},
        ],
    )
    def test_a_job_that_is_not_this_one_is_ignored(self, job: dict[str, Any]) -> None:
        assert _corroborate(jobs=[job]).reason == "checkrun.absent"

    def test_a_job_with_no_check_run_reads_unknown(self) -> None:
        got = _corroborate(checks={})
        assert (got.state, got.reason) == (EvidenceState.UNKNOWN, "checkrun.absent")

    @pytest.mark.parametrize("app", [{"id": 1}, {}, None, "github-actions", {"id": True}])
    def test_a_check_run_from_another_app_is_refused(self, app: Any) -> None:
        got = _corroborate(checks={JOB_ID: _check(app=app)})
        assert (got.state, got.reason) == (EvidenceState.UNKNOWN, "checkrun.app_mismatch")

    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": "Other"},
            {"details_url": f"https://github.com/{REPO}/actions/runs/1/job/{JOB_ID}"},
            {"details_url": f"https://github.com/other/repo/actions/runs/{RUN_ID}/job/{JOB_ID}"},
            {"details_url": f"https://evil.example/{REPO}/actions/runs/{RUN_ID}/job/{JOB_ID}"},
            {"details_url": None},
        ],
    )
    def test_a_check_run_that_does_not_name_this_job_is_refused(
        self, overrides: dict[str, Any]
    ) -> None:
        got = _corroborate(checks={JOB_ID: _check(**overrides)})
        assert (got.state, got.reason) == (EvidenceState.UNKNOWN, "checkrun.run_mismatch")

    def test_a_matrix_passes_only_when_every_leg_passes(self) -> None:
        jobs = [_job(id=1), _job(id=2)]
        both = {1: _check(1), 2: _check(2)}
        assert _corroborate(jobs, both).state is EvidenceState.PASS
        one_failed = {1: _check(1), 2: _check(2, conclusion="failure")}
        assert _corroborate(jobs, one_failed) == Corroboration(
            EvidenceState.FAIL, "checkrun.failure"
        )
        one_skipped = {1: _check(1), 2: _check(2, conclusion="skipped")}
        assert _corroborate(jobs, one_skipped).state is EvidenceState.UNKNOWN

    def test_a_matrix_with_one_unpinned_leg_does_not_pass(self) -> None:
        jobs = [_job(id=1), _job(id=2)]
        got = _corroborate(jobs, {1: _check(1), 2: _check(2, app={"id": 9})})
        assert got.state is EvidenceState.UNKNOWN

    @pytest.mark.parametrize(
        "repository",
        ["", "owner", "a/b/c", "o wner/repo", "owner/repo\n", "../..", "./repo", "o/.."],
    )
    def test_a_bad_repository_name_reads_unknown(self, repository: str) -> None:
        assert _corroborate(repository=repository).state is EvidenceState.UNKNOWN


def _record(state: EvidenceState = EvidenceState.PASS, **extra: Any) -> EvidenceRecord:
    document: dict[str, Any] = {
        "validator": "run_python_tests",
        "state": state.value,
        "revision": SHA,
        "scope": "job x on push",
    }
    if state is not EvidenceState.PASS:
        document["reason"] = "job.failed"
    else:
        document["findings"] = 0
    document.update(extra)
    return parse_evidence(document, "run_python_tests.json")


class TestCombine:
    def test_a_passing_artifact_with_a_passing_check_run_is_unchanged(self) -> None:
        record = _record()
        assert combine(record, Corroboration(EvidenceState.PASS)) is record

    def test_a_failing_check_run_downgrades_a_passing_artifact(self) -> None:
        got = combine(_record(), Corroboration(EvidenceState.FAIL, "checkrun.failure"))
        assert (got.outcome.state, got.outcome.reason) == (EvidenceState.FAIL, "checkrun.failure")
        assert got.outcome.revision == SHA
        assert isinstance(got.outcome, CheckOutcome)

    def test_an_unknown_check_run_downgrades_a_passing_artifact(self) -> None:
        got = combine(_record(), Corroboration(EvidenceState.UNKNOWN, "checkrun.absent"))
        assert got.outcome.state is EvidenceState.UNKNOWN

    def test_a_failing_artifact_keeps_its_own_state_over_a_passing_check_run(self) -> None:
        record = _record(EvidenceState.FAIL)
        assert combine(record, Corroboration(EvidenceState.PASS)) is record

    def test_a_failing_artifact_beats_an_unknown_check_run(self) -> None:
        record = _record(EvidenceState.FAIL)
        assert combine(record, Corroboration(EvidenceState.UNKNOWN, "checkrun.absent")) is record

    def test_a_skip_is_made_worse_by_an_unknown_check_run(self) -> None:
        record = _record(EvidenceState.SKIP)
        got = combine(record, Corroboration(EvidenceState.UNKNOWN, "checkrun.skipped"))
        assert got.outcome.state is EvidenceState.UNKNOWN

    def test_a_downgrade_keeps_the_digest_and_the_failed_items(self) -> None:
        record = _record(EvidenceState.SKIP, digest="c" * 64, items=["a.py"])
        got = combine(record, Corroboration(EvidenceState.FAIL, "checkrun.timed_out"))
        assert got.digest == "c" * 64
        assert got.items == ("a.py",)

    def test_a_downgraded_record_is_still_valid_evidence(self) -> None:
        got = combine(_record(), Corroboration(EvidenceState.UNKNOWN, "checkrun.absent", "why"))
        again = parse_evidence(got.outcome.to_dict(), "x")
        assert again.outcome.state is EvidenceState.UNKNOWN
        assert again.outcome.detail == "why"
