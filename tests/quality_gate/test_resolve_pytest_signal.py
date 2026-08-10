"""Tests for scripts/quality_gate/resolve_pytest_signal.py.

The resolver reads the verdict ``pytest.yml`` produced for a pull request head
so ``ai-pr-quality-gate.yml`` can stop re-running the suite (issue #4822).
Every ``gh`` call is faked. The fake dispatches on the argument vector rather
than on call order, so a branch that skips a call fails by name instead of
silently consuming the next canned response (testing rule 11).

The job fixtures mirror ``.github/workflows/pytest.yml`` as read on
2026-08-09: jobs ``test`` (line 111) and ``skip-tests`` (line 427) both declare
``name: Run Python Tests``, the first owning ``- name: Run pytest`` (line 260)
and the second owning ``- name: Skip tests (no Python test inputs changed)``
(line 441).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.quality_gate import resolve_pytest_signal as mod
from scripts.quality_gate.resolve_pytest_signal import (
    AGREE,
    DISAGREE,
    EXIT_CONFIG,
    EXIT_OK,
    STATUS_CANCELLED,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_STALE,
    STATUS_UNKNOWN,
    UNCOMPARED,
    Job,
    Run,
    aggregate,
    compare,
    main,
    parse_runs,
    sanitize,
    select_latest_run,
)

REPO = "rjmurillo/ai-agents"
PR = "4822"
HEAD = "a" * 40
OTHER_HEAD = "b" * 40

REF_PATH = f"repos/{REPO}/git/ref/pull/{PR}/head"
RUNS_PATH = (
    f"repos/{REPO}/actions/workflows/pytest.yml/runs"
    f"?event=pull_request&head_sha={HEAD}&per_page=100"
)


def jobs_path(run_id: int, attempt: int) -> str:
    return f"repos/{REPO}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class GhFake:
    """A ``gh`` stand-in that answers by path and records every call."""

    def __init__(self, responses: dict[str, tuple[int, str]]) -> None:
        self.responses = responses
        self.paths: list[str] = []

    def __call__(self, argv, *, timeout=None):  # a test double for run_gh
        assert list(argv)[0] == "api", f"unexpected gh subcommand {argv}"
        path = list(argv)[-1]
        self.paths.append(path)
        if path not in self.responses:
            raise AssertionError(f"unstubbed gh path {path}")
        code, body = self.responses[path]
        return subprocess.CompletedProcess(["gh", *argv], code, stdout=body, stderr="")


def ref_body(sha: str) -> str:
    return json.dumps({"ref": f"refs/pull/{PR}/head", "object": {"sha": sha, "type": "commit"}})


def runs_body(*runs: dict) -> str:
    return json.dumps({"total_count": len(runs), "workflow_runs": list(runs)})


def run_entry(
    run_id: int = 100,
    attempt: int = 1,
    event: str = "pull_request",
    head_sha: str = HEAD,
    started_at: str = "2026-08-09T10:00:00Z",
) -> dict:
    return {
        "id": run_id,
        "run_attempt": attempt,
        "event": event,
        "head_sha": head_sha,
        "run_started_at": started_at,
        "head_branch": "feature-branch",
    }


def jobs_body(*jobs: dict) -> str:
    return json.dumps({"total_count": len(jobs), "jobs": list(jobs)})


def executor_job(conclusion: str = "success", step_conclusion: str = "success") -> dict:
    """The ``test`` job of pytest.yml, which owns the ``Run pytest`` step."""
    return {
        "name": "Run Python Tests",
        "status": "completed",
        "conclusion": conclusion,
        "steps": [
            {"name": "Check if tests needed", "conclusion": "success"},
            {"name": "Run pytest", "conclusion": step_conclusion},
        ],
    }


def pass_through_job(conclusion: str = "success") -> dict:
    """The ``skip-tests`` job of pytest.yml, which never runs the suite."""
    return {
        "name": "Run Python Tests",
        "status": "completed",
        "conclusion": conclusion,
        "steps": [
            {"name": "Harden Runner", "conclusion": "success"},
            {"name": "Skip tests (no Python test inputs changed)", "conclusion": conclusion},
        ],
    }


def resolve_with(gh: GhFake) -> mod.Resolution:
    return mod.resolve(
        gh,
        repo=REPO,
        pr=PR,
        expected_sha=HEAD,
        workflow="pytest.yml",
        job_name="Run Python Tests",
    )


# ---------------------------------------------------------------------------
# Freshness: stale head and push rejection
# ---------------------------------------------------------------------------


class TestFreshness:
    def test_a_head_that_is_no_longer_live_is_stale(self) -> None:
        gh = GhFake({REF_PATH: (0, ref_body(OTHER_HEAD))})

        result = resolve_with(gh)

        assert result.status == STATUS_STALE
        assert result.reason == mod.REASON_STALE_HEAD

    def test_a_stale_head_never_queries_workflow_runs(self) -> None:
        """The run query is wasted work and could report another commit."""
        gh = GhFake({REF_PATH: (0, ref_body(OTHER_HEAD))})

        resolve_with(gh)

        assert gh.paths == [REF_PATH]

    def test_a_live_head_in_upper_case_is_not_stale(self) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD.upper())),
                RUNS_PATH: (0, runs_body()),
            }
        )

        assert resolve_with(gh).status == STATUS_PENDING

    def test_a_push_run_for_the_same_commit_is_rejected(self) -> None:
        """pytest.yml also triggers on push (line 19) with a different job set."""
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(run_entry(event="push"))),
            }
        )

        result = resolve_with(gh)

        assert result.status == STATUS_PENDING
        assert result.reason == mod.REASON_NO_RUN

    def test_a_run_for_a_different_commit_is_rejected(self) -> None:
        payload = json.loads(runs_body(run_entry(head_sha=OTHER_HEAD)))

        assert parse_runs(payload, HEAD) == []

    def test_a_push_run_is_dropped_even_when_the_api_filter_is_ignored(self) -> None:
        payload = json.loads(runs_body(run_entry(event="push"), run_entry(run_id=101)))

        assert [run.run_id for run in parse_runs(payload, HEAD) or []] == [101]


# ---------------------------------------------------------------------------
# Attempt selection
# ---------------------------------------------------------------------------


class TestAttemptSelection:
    def test_jobs_are_read_from_the_latest_attempt(self) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(run_entry(run_id=100, attempt=3))),
                jobs_path(100, 3): (0, jobs_body(executor_job())),
            }
        )

        assert resolve_with(gh).status == STATUS_PASS
        assert jobs_path(100, 3) in gh.paths

    def test_the_newest_run_wins_over_an_older_one(self) -> None:
        runs = [
            Run(run_id=100, attempt=4, started_at="2026-08-09T10:00:00Z"),
            Run(run_id=200, attempt=1, started_at="2026-08-09T11:00:00Z"),
        ]

        assert select_latest_run(runs).run_id == 200

    def test_the_highest_attempt_wins_when_start_times_tie(self) -> None:
        runs = [
            Run(run_id=100, attempt=1, started_at="2026-08-09T10:00:00Z"),
            Run(run_id=100, attempt=3, started_at="2026-08-09T10:00:00Z"),
        ]

        assert select_latest_run(runs).attempt == 3

    def test_a_missing_attempt_field_defaults_to_one(self) -> None:
        entry = run_entry()
        del entry["run_attempt"]
        payload = json.loads(runs_body(entry))

        assert (parse_runs(payload, HEAD) or [])[0].attempt == 1


# ---------------------------------------------------------------------------
# Executor and pass-through classification, duplicate-name severity
# ---------------------------------------------------------------------------


class TestJobAggregation:
    def test_an_executor_pass_is_pass(self) -> None:
        assert aggregate([mod.parse_job(executor_job())]).status == STATUS_PASS

    def test_a_sibling_failure_beats_a_sibling_success(self) -> None:
        """Both jobs are named "Run Python Tests"; the worst outcome wins."""
        jobs = [
            mod.parse_job(executor_job(conclusion="failure", step_conclusion="failure")),
            mod.parse_job(pass_through_job()),
        ]

        assert aggregate(jobs).status == STATUS_FAIL

    def test_a_failing_executor_is_not_rescued_by_a_passing_executor(self) -> None:
        jobs = [
            mod.parse_job(executor_job()),
            mod.parse_job(executor_job(conclusion="failure", step_conclusion="failure")),
        ]

        assert aggregate(jobs).status == STATUS_FAIL

    def test_a_pass_through_only_run_is_skipped_never_pass(self) -> None:
        """A green pass-through means the suite never ran (pytest.yml #1168)."""
        assert aggregate([mod.parse_job(pass_through_job())]).status == STATUS_SKIPPED

    def test_a_green_executor_whose_pytest_step_was_skipped_is_skipped(self) -> None:
        job = mod.parse_job(executor_job(conclusion="success", step_conclusion="skipped"))

        assert aggregate([job]).status == STATUS_SKIPPED

    def test_the_real_green_but_unrun_payload_is_skipped(self) -> None:
        """Regression pin taken from live API data, not from the fixtures above.

        Captured 2026-08-09 from
        ``GET /repos/rjmurillo/ai-agents/actions/runs/31360441685/attempts/1/jobs``.
        That run reports ``conclusion: success`` at the run level and BOTH jobs
        named "Run Python Tests" report ``conclusion: success``, yet the suite
        never executed: the pass-through job ran its skip step and the executor
        job ran with every step after "Check if tests needed" skipped. Any
        resolver reading the run conclusion, or either job conclusion, would
        report PASS for a commit nothing was tested on. Step names are the only
        discriminator, so this payload is pinned verbatim.
        """
        real_pass_through = {
            "name": "Run Python Tests",
            "status": "completed",
            "conclusion": "success",
            "steps": [
                {"name": "Set up job", "conclusion": "success"},
                {"name": "Skip tests (no Python test inputs changed)", "conclusion": "success"},
                {"name": "Complete job", "conclusion": "success"},
            ],
        }
        real_executor = {
            "name": "Run Python Tests",
            "status": "completed",
            "conclusion": "success",
            "steps": [
                {"name": "Set up job", "conclusion": "success"},
                {"name": "Check if tests needed", "conclusion": "success"},
                {"name": "Setup code environment", "conclusion": "skipped"},
                {"name": "Run pytest", "conclusion": "skipped"},
                {"name": "Upload test results", "conclusion": "skipped"},
                {"name": "Complete job", "conclusion": "success"},
            ],
        }
        jobs = [mod.parse_job(real_pass_through), mod.parse_job(real_executor)]

        assert aggregate(jobs).status == STATUS_SKIPPED

    def test_an_executor_decides_over_a_pass_through_sibling(self) -> None:
        jobs = [mod.parse_job(executor_job()), mod.parse_job(pass_through_job("skipped"))]

        assert aggregate(jobs).status == STATUS_PASS

    def test_an_incomplete_executor_is_pending(self) -> None:
        job = Job(name="Run Python Tests", status="in_progress", conclusion="", steps=())

        assert mod.executor_status(job) == STATUS_PENDING

    def test_a_cancelled_job_is_cancelled(self) -> None:
        job = mod.parse_job(executor_job(conclusion="cancelled", step_conclusion="cancelled"))

        assert aggregate([job]).status == STATUS_CANCELLED

    def test_a_timed_out_job_is_a_failure(self) -> None:
        job = mod.parse_job(executor_job(conclusion="timed_out", step_conclusion="failure"))

        assert aggregate([job]).status == STATUS_FAIL

    def test_a_job_with_no_recognizable_steps_cannot_report_pass(self) -> None:
        job = mod.parse_job(
            {"name": "Run Python Tests", "status": "completed", "conclusion": "success"}
        )

        assert aggregate([job]).status == STATUS_UNKNOWN

    def test_no_matching_job_is_unknown(self) -> None:
        result = aggregate([])

        assert result.status == STATUS_UNKNOWN
        assert result.reason == mod.REASON_NO_JOB

    def test_an_unrecognized_conclusion_is_unknown_and_says_so(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        job = mod.parse_job(executor_job(conclusion="action_required"))

        assert aggregate([job]).status == STATUS_UNKNOWN
        assert "unrecognized job conclusion" in capsys.readouterr().err

    def test_only_jobs_carrying_the_check_name_are_considered(self) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(run_entry())),
                jobs_path(100, 1): (
                    0,
                    jobs_body(
                        {
                            "name": "Python Security Checks",
                            "status": "completed",
                            "conclusion": "failure",
                            "steps": [{"name": "Run Bandit", "conclusion": "failure"}],
                        },
                        executor_job(),
                    ),
                ),
            }
        )

        assert resolve_with(gh).status == STATUS_PASS


# ---------------------------------------------------------------------------
# Missing, pending, and unusable API data
# ---------------------------------------------------------------------------


class TestUnusableData:
    def test_no_run_yet_is_pending(self) -> None:
        gh = GhFake({REF_PATH: (0, ref_body(HEAD)), RUNS_PATH: (0, runs_body())})

        result = resolve_with(gh)

        assert result.status == STATUS_PENDING
        assert result.reason == mod.REASON_NO_RUN

    def test_a_queued_job_is_pending(self) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(run_entry())),
                jobs_path(100, 1): (
                    0,
                    jobs_body(
                        {
                            "name": "Run Python Tests",
                            "status": "queued",
                            "conclusion": None,
                            "steps": [{"name": "Run pytest", "conclusion": None}],
                        }
                    ),
                ),
            }
        )

        assert resolve_with(gh).status == STATUS_PENDING

    def test_a_cancelled_run_reports_cancelled(self) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(run_entry())),
                jobs_path(100, 1): (
                    0,
                    jobs_body(executor_job(conclusion="cancelled", step_conclusion="cancelled")),
                ),
            }
        )

        assert resolve_with(gh).status == STATUS_CANCELLED

    def test_a_forbidden_run_query_is_unknown(self) -> None:
        """A 403 from a missing actions scope must not read as a verdict."""
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (1, json.dumps({"message": "Resource not accessible"})),
            }
        )

        result = resolve_with(gh)

        assert result.status == STATUS_UNKNOWN
        assert result.reason == mod.REASON_RUNS_UNREADABLE

    def test_a_forbidden_ref_query_is_unknown(self) -> None:
        gh = GhFake({REF_PATH: (1, "")})

        result = resolve_with(gh)

        assert result.status == STATUS_UNKNOWN
        assert result.reason == mod.REASON_LIVE_HEAD_UNREADABLE

    def test_a_gh_binary_that_cannot_launch_is_unknown(self) -> None:
        def exploding(argv, *, timeout=None):
            raise FileNotFoundError("gh")

        result = mod.resolve(
            exploding,
            repo=REPO,
            pr=PR,
            expected_sha=HEAD,
            workflow="pytest.yml",
            job_name="Run Python Tests",
        )

        assert result.status == STATUS_UNKNOWN

    def test_invalid_json_is_unknown(self) -> None:
        gh = GhFake({REF_PATH: (0, "not json at all")})

        assert resolve_with(gh).status == STATUS_UNKNOWN

    def test_a_ref_payload_without_a_sha_is_unknown(self) -> None:
        gh = GhFake({REF_PATH: (0, json.dumps({"ref": "refs/pull/1/head"}))})

        result = resolve_with(gh)

        assert result.status == STATUS_UNKNOWN
        assert result.reason == mod.REASON_LIVE_HEAD_MALFORMED

    def test_a_truncated_sha_is_not_accepted_as_the_live_head(self) -> None:
        gh = GhFake({REF_PATH: (0, ref_body("a" * 39))})

        assert resolve_with(gh).reason == mod.REASON_LIVE_HEAD_MALFORMED

    def test_a_run_list_that_is_not_a_list_is_unknown(self) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, json.dumps({"workflow_runs": "nope"})),
            }
        )

        assert resolve_with(gh).reason == mod.REASON_RUNS_UNREADABLE

    def test_a_job_list_that_is_not_a_list_is_unknown(self) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(run_entry())),
                jobs_path(100, 1): (0, json.dumps({"jobs": {"name": "Run Python Tests"}})),
            }
        )

        assert resolve_with(gh).reason == mod.REASON_JOBS_UNREADABLE

    def test_a_run_entry_without_an_id_is_dropped(self) -> None:
        entry = run_entry()
        entry["id"] = "not-a-number"

        assert parse_runs(json.loads(runs_body(entry)), HEAD) == []

    def test_a_non_mapping_payload_is_unusable(self) -> None:
        assert parse_runs(["a list"], HEAD) is None


# ---------------------------------------------------------------------------
# Comparison against the local run
# ---------------------------------------------------------------------------


class TestCompare:
    def test_matching_statuses_agree(self) -> None:
        assert compare(STATUS_PASS, "PASS")[0] == AGREE

    def test_differing_statuses_disagree(self) -> None:
        assert compare(STATUS_PENDING, "PASS")[0] == DISAGREE

    def test_a_missing_local_status_is_uncompared(self) -> None:
        assert compare(STATUS_PASS, "")[0] == UNCOMPARED

    def test_an_unknown_local_token_is_uncompared(self) -> None:
        assert compare(STATUS_PASS, "TOTALLY_MADE_UP")[0] == UNCOMPARED

    def test_a_lower_case_local_status_still_agrees(self) -> None:
        assert compare(STATUS_FAIL, " fail ")[0] == AGREE


# ---------------------------------------------------------------------------
# Output sanitation
# ---------------------------------------------------------------------------


class TestSanitation:
    def test_workflow_command_syntax_cannot_survive(self) -> None:
        assert "::" not in sanitize("::error::title=pwned")

    def test_newlines_cannot_survive(self) -> None:
        assert "\n" not in sanitize("first line\nsecond line")

    def test_percent_escapes_cannot_survive(self) -> None:
        assert "%" not in sanitize("%0A%0Dinjected")

    def test_output_is_truncated(self) -> None:
        assert len(sanitize("x" * 500)) == 160

    def test_emit_sanitizes_a_reason_it_is_handed(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The second line of defence, reached only if a reason ever carries text.

        Every reason this module builds is already a fixed constant, so no
        resolve-level input can exercise this. Constructing the Resolution
        directly is the only input on which a sanitizing and a non-sanitizing
        ``emit`` disagree, which is what makes the guard testable at all.
        """
        hostile = mod.Resolution(STATUS_FAIL, "::error::title=x\nsecond line")

        outputs = mod.emit(hostile, DISAGREE, "::error::agreement")

        printed = capsys.readouterr().out
        assert outputs["shadow_pytest_reason"] == "errortitlex second line"
        assert "::error::" not in printed
        assert printed.count("::warning::") == 1

    def test_no_fork_controlled_text_reaches_the_outputs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Branch, title, and commit text from the payload must never be emitted."""
        poison = "::error::PWNED"
        hostile_run = run_entry()
        hostile_run["head_branch"] = f"{poison}-branch"
        hostile_run["display_title"] = f"{poison}-title"
        hostile_run["head_commit"] = {"message": f"{poison}-commit\nsecond line"}
        hostile_job = executor_job()
        hostile_job["workflow_name"] = f"{poison}-workflow"
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(hostile_run)),
                jobs_path(100, 1): (0, jobs_body(hostile_job)),
            }
        )
        monkeypatch.setattr(mod, "run_gh", gh)
        output_file = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        code = main(
            ["--repo", REPO, "--pr", PR, "--expected-head-sha", HEAD, "--local-status", "PASS"]
        )

        captured = capsys.readouterr()
        written = output_file.read_text(encoding="utf-8")
        assert code == EXIT_OK
        for surface in (captured.out, captured.err, written):
            assert "PWNED" not in surface
            assert "::error::" not in surface
        assert "shadow_pytest_status=PASS" in written
        assert written.endswith("\n")
        assert len(written.strip().splitlines()) == 3


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


class TestMain:
    def test_a_malformed_expected_sha_exits_config(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["--repo", REPO, "--pr", PR, "--expected-head-sha", "abc123"])

        assert code == EXIT_CONFIG
        assert "40 hex" in capsys.readouterr().err

    def test_a_missing_expected_sha_exits_config(self) -> None:
        assert main(["--repo", REPO, "--pr", PR, "--expected-head-sha", ""]) == EXIT_CONFIG

    def test_a_malformed_repo_exits_config(self) -> None:
        argv = ["--repo", "not-a-repo", "--pr", PR, "--expected-head-sha", HEAD]

        assert main(argv) == EXIT_CONFIG

    def test_a_non_numeric_pr_exits_config(self) -> None:
        argv = ["--repo", REPO, "--pr", "../../etc", "--expected-head-sha", HEAD]

        assert main(argv) == EXIT_CONFIG

    def test_a_workflow_name_with_a_path_exits_config(self) -> None:
        argv = [
            "--repo",
            REPO,
            "--pr",
            PR,
            "--expected-head-sha",
            HEAD,
            "--workflow",
            "../../../etc/passwd",
        ]

        assert main(argv) == EXIT_CONFIG

    def test_a_resolution_failure_still_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Shadow mode observes. An API failure must not change the job outcome."""
        gh = GhFake({REF_PATH: (1, "")})
        monkeypatch.setattr(mod, "run_gh", gh)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

        code = main(["--repo", REPO, "--pr", PR, "--expected-head-sha", HEAD])

        assert code == EXIT_OK
        assert "shadow_pytest_status=UNKNOWN" in capsys.readouterr().out

    def test_a_disagreement_emits_a_warning_annotation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        gh = GhFake({REF_PATH: (0, ref_body(HEAD)), RUNS_PATH: (0, runs_body())})
        monkeypatch.setattr(mod, "run_gh", gh)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

        main(["--repo", REPO, "--pr", PR, "--expected-head-sha", HEAD, "--local-status", "PASS"])

        out = capsys.readouterr().out
        assert "shadow_pytest_agreement=DISAGREE" in out
        assert "::warning::Shadow pytest signal disagreement." in out

    def test_agreement_emits_no_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        gh = GhFake(
            {
                REF_PATH: (0, ref_body(HEAD)),
                RUNS_PATH: (0, runs_body(run_entry())),
                jobs_path(100, 1): (0, jobs_body(executor_job())),
            }
        )
        monkeypatch.setattr(mod, "run_gh", gh)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

        main(["--repo", REPO, "--pr", PR, "--expected-head-sha", HEAD, "--local-status", "PASS"])

        out = capsys.readouterr().out
        assert "shadow_pytest_agreement=AGREE" in out
        assert "::warning::" not in out

    def test_env_vars_supply_the_defaults(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        gh = GhFake({REF_PATH: (0, ref_body(OTHER_HEAD))})
        monkeypatch.setattr(mod, "run_gh", gh)
        monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
        monkeypatch.setenv("PR_NUMBER", PR)
        monkeypatch.setenv("EXPECTED_HEAD_SHA", HEAD)
        monkeypatch.setenv("LOCAL_PYTEST_STATUS", "PASS")
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

        assert main([]) == EXIT_OK
        assert "shadow_pytest_status=STALE" in capsys.readouterr().out
