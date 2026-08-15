"""Tests for the shadow pytest signal resolver and workflow wiring."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.quality_gate import resolve_pytest_signal as mod
from scripts.quality_gate.resolve_pytest_signal import Job, Resolution, Run

AGREE, DISAGREE, UNCOMPARED = mod.AGREE, mod.DISAGREE, mod.UNCOMPARED
EXIT_OK, EXIT_CONFIG = mod.EXIT_OK, mod.EXIT_CONFIG
aggregate, compare, main, sanitize = mod.aggregate, mod.compare, mod.main, mod.sanitize
select_latest_run, NO_RUN = mod.select_latest_run, mod.REASON_NO_RUN
STATUS_PASS, STATUS_FAIL, STATUS_SKIPPED = mod.STATUS_PASS, mod.STATUS_FAIL, mod.STATUS_SKIPPED
STATUS_PENDING, STATUS_STALE = mod.STATUS_PENDING, mod.STATUS_STALE
STATUS_CANCELLED, STATUS_UNKNOWN = mod.STATUS_CANCELLED, mod.STATUS_UNKNOWN
Capsys = pytest.CaptureFixture[str]

REPO = "rjmurillo/ai-agents"
PR = "4822"
HEAD = "a" * 40
OTHER_HEAD = "b" * 40
CHECK = "Run Python Tests"
SKIP_STEP = "Skip tests (no Python test inputs changed)"

REF_PATH = f"repos/{REPO}/git/ref/pull/{PR}/head"
_RUNS_QUERY = "actions/workflows/pytest.yml/runs?event=pull_request&head_sha="
RUNS_PATH = f"repos/{REPO}/{_RUNS_QUERY}{HEAD}&per_page=100"


def jobs_path(attempt: int = 1) -> str:
    return f"repos/{REPO}/actions/runs/100/attempts/{attempt}/jobs?per_page=100"


class GhFake:
    """A ``gh`` stand-in that answers by path and records every call."""

    def __init__(self, responses: dict[str, tuple[int, str]]) -> None:
        self.responses = responses
        self.paths: list[str] = []

    def __call__(self, argv, *, timeout=None):  # a test double for run_gh
        assert list(argv)[0] == "api", f"unexpected gh subcommand {argv}"
        self.paths.append(path := list(argv)[-1])
        assert path in self.responses, f"unstubbed gh path {path}"
        code, body = self.responses[path]
        return subprocess.CompletedProcess(["gh", *argv], code, stdout=body, stderr="")


def run_entry(prs: tuple[int, ...] = (int(PR),), repo: str | None = REPO, **over: object) -> dict:
    """One run entry, mirroring the live list endpoint read 2026-08-10.

    Runs of open pull requests carry their own number in ``pull_requests`` and
    same-repo runs name the upstream in ``head_repository``; ``repo=None`` omits
    that key, as a payload missing it would. Overrides use the live key names.
    """
    return {
        "id": 100,
        "run_attempt": 1,
        "event": "pull_request",
        "head_sha": HEAD,
        "run_started_at": "2026-08-09T10:00:00Z",
        "head_branch": "feature-branch",
        "pull_requests": [{"number": number} for number in prs],
        **({} if repo is None else {"head_repository": {"full_name": repo}}),
        **over,
    }


def executor(conclusion: str = "success", step: str = "success") -> dict:
    steps = [{"name": "Check if tests needed", "conclusion": "success"}]
    steps.append({"name": "Run pytest", "conclusion": step})
    return {"name": CHECK, "status": "completed", "conclusion": conclusion, "steps": steps}


def pass_through(conclusion: str = "success") -> dict:
    steps = [{"name": "Harden Runner", "conclusion": "success"}]
    steps.append({"name": SKIP_STEP, "conclusion": conclusion})
    return {"name": CHECK, "status": "completed", "conclusion": conclusion, "steps": steps}


def bare(status: str = "completed", conclusion: str | None = "success") -> dict:
    """A job holding the required check name but no step this module knows."""
    return {"name": CHECK, "status": status, "conclusion": conclusion}


def parsed(*jobs: dict) -> list[Job]:
    return [mod.parse_job(job) for job in jobs]


def gh_stub(
    *,
    ref: str = HEAD,
    runs: list[dict] | None = None,
    jobs: list[dict] | None = None,
    attempt: int = 1,
    raw: dict[str, tuple[int, str]] | None = None,
) -> GhFake:
    """Stub only the endpoints a test names; ``raw`` replaces one verbatim.

    An unstubbed endpoint raises by path, so a resolver that queries what it
    should have skipped fails loudly rather than silently.
    """
    responses = {REF_PATH: (0, json.dumps({"object": {"sha": ref, "type": "commit"}}))}
    if runs is not None:
        responses[RUNS_PATH] = (0, json.dumps({"workflow_runs": runs}))
    if jobs is not None:
        responses[jobs_path(attempt)] = (0, json.dumps({"jobs": jobs}))
    return GhFake({**responses, **(raw or {})})


def resolve_with(gh) -> Resolution:
    return mod.resolve(
        gh, repo=REPO, pr=PR, expected_sha=HEAD, workflow="pytest.yml", job_name=CHECK
    )


def resolved(**stub: Any) -> Resolution:
    return resolve_with(gh_stub(**stub))


def scan(*runs: dict) -> tuple[tuple[Run, ...], int]:
    """Parse a runs payload the caller expects to be usable, failing by name."""
    result = mod.parse_runs({"workflow_runs": list(runs)}, HEAD, pr=PR, repo=REPO)
    assert result is not None, "the payload should have parsed"
    return result


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch):
    """Invoke ``main`` against a stubbed ``gh``, with GITHUB_OUTPUT unset."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    def run(gh: GhFake, *extra: str) -> int:
        monkeypatch.setattr(mod, "run_gh", gh)
        return main(["--repo", REPO, "--pr", PR, "--expected-head-sha", HEAD, *extra])

    return run


class TestFreshness:
    def test_a_head_that_is_no_longer_live_is_stale(self) -> None:
        assert resolved(ref=OTHER_HEAD) == Resolution(STATUS_STALE, mod.REASON_STALE_HEAD)

    def test_a_stale_head_never_queries_workflow_runs(self) -> None:
        """The run query is wasted work and could report another commit."""
        gh = gh_stub(ref=OTHER_HEAD)
        resolve_with(gh)
        assert gh.paths == [REF_PATH]

    def test_an_upper_case_expected_head_is_not_stale(self) -> None:
        gh = gh_stub(runs=[])
        result = mod.resolve(
            gh, repo=REPO, pr=PR, expected_sha=HEAD.upper(), workflow="pytest.yml", job_name=CHECK
        )
        assert result.status == STATUS_PENDING

    def test_a_push_run_for_the_same_commit_is_rejected(self) -> None:
        """pytest.yml also triggers on push, with a different job set."""
        assert resolved(runs=[run_entry(event="push")]) == Resolution(STATUS_PENDING, NO_RUN)

    def test_a_push_run_is_dropped_even_when_the_api_filter_is_ignored(self) -> None:
        """The query string asks for pull_request runs; this filter guarantees."""
        bound, _ = scan(run_entry(event="push"), run_entry(id=101))
        assert [run.run_id for run in bound] == [101]


class TestPullRequestBinding:
    # GitHub empties pull_requests[] once a pull request closes: verified live
    # 2026-08-10, where every run of the merged pull request 4819 reported an
    # empty list while runs of the open 4832, 4833, and 4834 carried their own.
    # An empty list is therefore normal and never a failure by itself, and the
    # same-repo fallback holds because a fork cannot be named upstream. A run
    # that binds to nobody is counted, not dropped, so the caller can tell
    # "nothing has run yet" from "something ran for someone else".
    _CASES = {
        "another-pull-request": (run_entry(prs=(9999,)), 0, 1),
        "several-including-ours": (run_entry(prs=(9999, int(PR))), 1, 0),
        "empty-list-same-repo": (run_entry(prs=()), 1, 0),
        "empty-list-fork": (run_entry(prs=(), repo="attacker/ai-agents"), 0, 1),
        "empty-list-no-head-repository": (run_entry(prs=(), repo=None), 0, 1),
        "malformed-link-falls-back": (run_entry(repo=None, pull_requests=["not a mapping"]), 0, 1),
        "repo-case-differs": (run_entry(prs=(), repo=REPO.upper()), 1, 0),
        "number-prefix-is-no-match": (run_entry(prs=(int(PR + "0"),)), 0, 1),
        "another-commit": (run_entry(head_sha=OTHER_HEAD), 0, 0),
        "non-numeric-run-id": (run_entry(id="not-a-number"), 0, 0),
    }

    @pytest.mark.parametrize(("entry", "bound", "rejected"), _CASES.values(), ids=_CASES)
    def test_a_run_binds_only_when_it_provably_belongs_to_us(self, entry, bound, rejected) -> None:
        found, refused = scan(entry)
        assert len(found) == bound
        assert refused == rejected

    def test_a_colliding_sibling_run_does_not_hide_our_own_run(self) -> None:
        bound, rejected = scan(run_entry(id=101, prs=(9999,)), run_entry(id=100))
        assert [run.run_id for run in bound] == [100]
        assert rejected == 1

    def test_only_another_pull_requests_run_resolves_unknown_not_pending(self) -> None:
        """ "Someone else's run" must not read as "nothing has run yet"."""
        unbound = Resolution(STATUS_UNKNOWN, mod.REASON_RUN_NOT_BOUND)
        assert resolved(runs=[run_entry(prs=(9999,))]) == unbound


class TestAttemptSelection:
    def test_jobs_are_read_from_the_latest_attempt(self) -> None:
        gh = gh_stub(runs=[run_entry(run_attempt=3)], jobs=[executor()], attempt=3)
        assert resolve_with(gh).status == STATUS_PASS
        assert jobs_path(3) in gh.paths

    def test_the_newest_run_wins_over_an_older_one(self) -> None:
        older = Run(run_id=100, attempt=4, started_at="2026-08-09T10:00:00Z")
        newer = Run(run_id=200, attempt=1, started_at="2026-08-09T11:00:00Z")
        assert select_latest_run([older, newer]).run_id == 200

    def test_the_highest_attempt_wins_when_start_times_tie(self) -> None:
        first = Run(run_id=100, attempt=1, started_at="2026-08-09T10:00:00Z")
        rerun = Run(run_id=100, attempt=3, started_at="2026-08-09T10:00:00Z")
        assert select_latest_run([first, rerun]).attempt == 3

    def test_a_missing_attempt_field_defaults_to_one(self) -> None:
        entry = run_entry()
        del entry["run_attempt"]
        assert scan(entry)[0][0].attempt == 1


class TestJobAggregation:
    # Every job here carries the required check name, so the first non-empty
    # tier decides and a lower tier can overrule it downward but never upward.
    # "benign-skipped-sibling" is the inverse guard, taken from the live shape
    # of run 31355229018: were SKIPPED to escalate, every ordinary green pull
    # request would resolve to SKIPPED.
    _TIERS = {
        "executor-pass": ([executor()], STATUS_PASS),
        "sibling-failure-wins": ([executor("failure", "failure"), pass_through()], STATUS_FAIL),
        "failing-executor-not-rescued": ([executor(), executor("failure", "failure")], STATUS_FAIL),
        "pass-through-only-never-passes": ([pass_through()], STATUS_SKIPPED),
        "green-executor-that-skipped": ([executor("success", "skipped")], STATUS_SKIPPED),
        "executor-outranks-pass-through": ([executor(), pass_through("skipped")], STATUS_PASS),
        "skip-hides-no-fail": (
            [executor("success", "skipped"), pass_through("failure")],
            STATUS_FAIL,
        ),
        "executor-pass-hides-no-fail": ([executor(), bare(conclusion="failure")], STATUS_FAIL),
        "pass-through-hides-no-fail": ([pass_through(), bare(conclusion="failure")], STATUS_FAIL),
        "unclassified-tier-hides-no-fail": ([bare(), bare(conclusion="failure")], STATUS_FAIL),
        "running-sibling-holds-open": ([executor(), bare("in_progress", None)], STATUS_PENDING),
        "benign-skipped-sibling": ([executor(), bare(conclusion="skipped")], STATUS_PASS),
        "unclassifiable-sibling-benign": ([executor(), bare()], STATUS_PASS),
        "blocking-unknown-sibling-holds-open": (
            [executor(), bare(conclusion="action_required")],
            STATUS_UNKNOWN,
        ),
        "cancelled": ([executor("cancelled", "cancelled")], STATUS_CANCELLED),
        "timed-out-is-a-failure": ([executor("timed_out", "failure")], STATUS_FAIL),
        "no-known-step-cannot-pass": ([bare()], STATUS_UNKNOWN),
    }

    @pytest.mark.parametrize(("jobs", "status"), _TIERS.values(), ids=_TIERS)
    def test_same_named_jobs_reduce_to_one_status(self, jobs: list[dict], status: str) -> None:
        assert aggregate(parsed(*jobs)).status == status

    def test_an_executor_pass_does_not_mask_a_pass_through_failure(self) -> None:
        """A failed pass-through is a red check; PASS would claim a green one."""
        result = aggregate(parsed(executor(), pass_through("failure")))
        assert result.status == STATUS_FAIL
        assert "unhealthy sibling" in result.reason

    def test_the_real_green_but_unrun_payload_is_skipped(self) -> None:
        """Pin the live green-but-unrun payload from run 31360441685."""
        payload = json.loads("""{"jobs": [
          {"name": "Run Python Tests", "status": "completed", "conclusion": "success", "steps": [
            {"name": "Set up job", "conclusion": "success"},
            {"name": "Skip tests (no Python test inputs changed)", "conclusion": "success"},
            {"name": "Complete job", "conclusion": "success"}]},
          {"name": "Run Python Tests", "status": "completed", "conclusion": "success", "steps": [
            {"name": "Set up job", "conclusion": "success"},
            {"name": "Check if tests needed", "conclusion": "success"},
            {"name": "Setup code environment", "conclusion": "skipped"},
            {"name": "Run pytest", "conclusion": "skipped"},
            {"name": "Upload test results", "conclusion": "skipped"},
            {"name": "Complete job", "conclusion": "success"}]}]}""")
        assert aggregate(parsed(*payload["jobs"])).status == STATUS_SKIPPED

    def test_an_incomplete_executor_is_pending(self) -> None:
        job = Job(name=CHECK, status="in_progress", conclusion="", steps=())
        assert mod.job_status(job, mod.KIND_EXECUTOR) == STATUS_PENDING

    def test_no_matching_job_is_unknown(self) -> None:
        assert aggregate([]) == Resolution(STATUS_UNKNOWN, mod.REASON_NO_JOB)

    def test_an_unrecognized_conclusion_is_unknown_and_says_so(self, capsys: Capsys) -> None:
        assert aggregate(parsed(executor("action_required"))).status == STATUS_UNKNOWN
        assert "unrecognized job conclusion" in capsys.readouterr().err

    def test_only_jobs_carrying_the_check_name_are_considered(self) -> None:
        other = {"name": "Python Security Checks", "status": "completed", "conclusion": "failure"}
        result = resolved(runs=[run_entry()], jobs=[other, executor()])
        assert result.status == STATUS_PASS


class TestUnusableData:
    # A 403 from a missing actions scope, a malformed body, and a body of the
    # wrong shape are all "no usable data", never a verdict.
    _MALFORMED = mod.REASON_LIVE_HEAD_MALFORMED
    _CASES = {
        "ref-forbidden": ({REF_PATH: (1, "")}, mod.REASON_LIVE_HEAD_UNREADABLE),
        "ref-invalid-json": ({REF_PATH: (0, "not json at all")}, mod.REASON_LIVE_HEAD_UNREADABLE),
        "ref-without-a-sha": ({REF_PATH: (0, '{"ref": "x"}')}, _MALFORMED),
        "ref-sha-short": ({REF_PATH: (0, json.dumps({"object": {"sha": "a" * 39}}))}, _MALFORMED),
        "runs-forbidden": ({RUNS_PATH: (1, '{"message": "no"}')}, mod.REASON_RUNS_UNREADABLE),
        "runs-not-a-list": ({RUNS_PATH: (0, '{"workflow_runs": 1}')}, mod.REASON_RUNS_UNREADABLE),
        "runs-not-an-object": ({RUNS_PATH: (0, '["a list"]')}, mod.REASON_RUNS_UNREADABLE),
    }

    @pytest.mark.parametrize(("raw", "reason"), _CASES.values(), ids=_CASES)
    def test_unusable_api_data_is_unknown(self, raw, reason) -> None:
        assert resolved(raw=raw) == Resolution(STATUS_UNKNOWN, reason)

    def test_no_run_yet_is_pending(self) -> None:
        assert resolved(runs=[]) == Resolution(STATUS_PENDING, NO_RUN)

    def test_a_queued_job_is_pending(self) -> None:
        queued = {**bare("queued", None), "steps": [{"name": "Run pytest", "conclusion": None}]}
        assert resolved(runs=[run_entry()], jobs=[queued]).status == STATUS_PENDING

    def test_a_cancelled_run_reports_cancelled(self) -> None:
        jobs = [executor("cancelled", "cancelled")]
        assert resolved(runs=[run_entry()], jobs=jobs).status == STATUS_CANCELLED

    def test_a_job_list_that_is_not_a_list_is_unknown(self) -> None:
        raw = {jobs_path(): (0, '{"jobs": {"name": "x"}}')}
        assert resolved(runs=[run_entry()], raw=raw).reason == mod.REASON_JOBS_UNREADABLE

    def test_a_gh_binary_that_cannot_launch_is_unknown(self) -> None:
        def exploding(argv, *, timeout=None):
            raise FileNotFoundError("gh")

        assert resolve_with(exploding).status == STATUS_UNKNOWN


class TestReporting:
    @pytest.mark.parametrize(
        ("status", "local", "agreement"),
        [
            (STATUS_PASS, "PASS", AGREE),
            (STATUS_PENDING, "PASS", DISAGREE),
            (STATUS_PASS, "", UNCOMPARED),
            (STATUS_PASS, "TOTALLY_MADE_UP", UNCOMPARED),
            (STATUS_FAIL, " fail ", AGREE),
        ],
    )
    def test_a_local_status_is_compared_with_the_resolved_one(self, status, local, agreement):
        assert compare(status, local)[0] == agreement

    @pytest.mark.parametrize(
        ("status", "agreement"), [(STATUS_PASS, AGREE), (STATUS_UNKNOWN, UNCOMPARED)]
    )
    def test_every_invocation_emits_exactly_one_sample_marker(self, status, agreement, capsys):
        """Zero samples must be countable, not invisible."""
        mod.emit(Resolution(status, "reason"), agreement, "reason")
        assert capsys.readouterr().out.count(mod.SAMPLE_MARKER) == 1

    @pytest.mark.parametrize(
        ("agreement", "compared"), [(AGREE, "true"), (DISAGREE, "true"), (UNCOMPARED, "false")]
    )
    def test_the_compared_flag_counts_only_real_comparisons(self, agreement, compared) -> None:
        """A disagreement is still a collected sample; an uncompared run is not."""
        outputs = mod.emit(Resolution(STATUS_PASS, "reason"), agreement, "reason")
        assert outputs["shadow_pytest_compared"] == compared

    def test_collecting_no_sample_is_warned_not_passed_over_quietly(self, capsys: Capsys) -> None:
        mod.emit(Resolution(STATUS_UNKNOWN, "reason"), UNCOMPARED, "no local status")
        assert "::warning::Shadow pytest signal collected no sample." in capsys.readouterr().out

    def test_a_healthy_agreement_raises_no_warning(self, capsys: Capsys) -> None:
        """The inverse guard: liveness reporting must not become noise."""
        mod.emit(Resolution(STATUS_PASS, "reason"), AGREE, "both report PASS")
        assert "::warning::" not in capsys.readouterr().out

    def test_the_marker_line_carries_the_status_and_agreement(self, capsys: Capsys) -> None:
        mod.emit(Resolution(STATUS_SKIPPED, "reason"), DISAGREE, "differ")
        marker = f"::notice::{mod.SAMPLE_MARKER} status=SKIPPED agreement=DISAGREE"
        assert marker in capsys.readouterr().out

    def test_the_no_sample_warning_sanitizes_the_reason_it_is_handed(self, capsys: Capsys) -> None:
        """The no-sample branch needs its own guard, not the disagree branch's.

        A mutant emitting the raw reason here survived until this test existed,
        so the guard was untested on the one path it protects.
        """
        mod.emit(Resolution(STATUS_UNKNOWN, "reason"), UNCOMPARED, "::error::title=x\nsecond")
        out = capsys.readouterr().out
        assert "::error::" not in out
        assert out.count("::warning::") == 1
        assert "errortitlex second" in out

    @pytest.mark.parametrize(
        ("hostile", "forbidden"),
        [("::error::title=pwned", "::"), ("line one\nline two", "\n"), ("%0A%0Dinjected", "%")],
    )
    def test_injection_syntax_cannot_survive(self, hostile: str, forbidden: str) -> None:
        assert forbidden not in sanitize(hostile)

    def test_output_is_truncated(self) -> None:
        assert len(sanitize("x" * 500)) == 160

    def test_emit_sanitizes_a_reason_it_is_handed(self, capsys: Capsys) -> None:
        hostile = Resolution(STATUS_FAIL, "::error::title=x\nsecond line")
        outputs = mod.emit(hostile, DISAGREE, "::error::agreement")
        printed = capsys.readouterr().out
        assert outputs["shadow_pytest_reason"] == "errortitlex second line"
        assert "::error::" not in printed
        assert printed.count("::warning::") == 1

    def test_no_fork_controlled_text_reaches_the_outputs(self, cli, monkeypatch, tmp_path, capsys):
        """Branch, title, and commit text are attacker-controlled on a fork."""
        poison = "::error::PWNED"
        run = run_entry(head_branch=poison, head_commit={"message": f"{poison}\nsecond line"})
        job = {**executor(), "workflow_name": poison}
        out_file = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

        assert cli(gh_stub(runs=[run], jobs=[job]), "--local-status", "PASS") == EXIT_OK

        captured = capsys.readouterr()
        written = out_file.read_text(encoding="utf-8")
        for surface in (captured.out, captured.err, written):
            assert "PWNED" not in surface and "::error::" not in surface
        assert "shadow_pytest_status=PASS" in written and written.endswith("\n")
        # Exactly the documented output keys, one per line, nothing smuggled in.
        keys = [line.split("=", 1)[0] for line in written.strip().splitlines()]
        assert keys == [f"shadow_pytest_{n}" for n in "status reason agreement compared".split()]


class TestMain:
    _INVALID = {
        "missing-sha": (["--expected-head-sha", ""], "40 hex"),
        "malformed-sha": (["--expected-head-sha", "abc123"], "40 hex"),
        "malformed-repo": (["--repo", "not-a-repo"], "owner/repo"),
        "non-numeric-pr": (["--pr", "../../etc"], "positive integer"),
        "workflow-with-a-path": (["--workflow", "../../etc/passwd"], "workflow file name"),
        "zero-timeout": (["--timeout", "0"], "finite positive"),
        "infinite-timeout": (["--timeout", "inf"], "finite positive"),
    }

    @pytest.mark.parametrize(("extra", "message"), _INVALID.values(), ids=_INVALID)
    def test_an_invalid_invocation_exits_config(self, extra, message, capsys):
        base = ["--repo", REPO, "--pr", PR, "--expected-head-sha", HEAD]
        assert main([*base, *extra]) == EXIT_CONFIG
        assert message in capsys.readouterr().err

    def test_a_resolution_failure_still_exits_zero(self, cli, capsys: Capsys) -> None:
        """Shadow mode observes. An API failure must not change the job outcome."""
        assert cli(gh_stub(raw={REF_PATH: (1, "")})) == EXIT_OK
        assert "shadow_pytest_status=UNKNOWN" in capsys.readouterr().out

    def test_a_disagreement_emits_a_warning_annotation(self, cli, capsys: Capsys) -> None:
        cli(gh_stub(runs=[]), "--local-status", "PASS")
        out = capsys.readouterr().out
        assert "shadow_pytest_agreement=DISAGREE" in out
        assert "::warning::Shadow pytest signal disagreement." in out

    def test_agreement_emits_no_warning(self, cli, capsys: Capsys) -> None:
        cli(gh_stub(runs=[run_entry()], jobs=[executor()]), "--local-status", "PASS")
        out = capsys.readouterr().out
        assert "shadow_pytest_agreement=AGREE" in out
        assert "::warning::" not in out

    def test_env_vars_supply_the_defaults(self, monkeypatch, capsys):
        monkeypatch.setattr(mod, "run_gh", gh_stub(ref=OTHER_HEAD))
        env = {"GITHUB_REPOSITORY": REPO, "PR_NUMBER": PR, "EXPECTED_HEAD_SHA": HEAD}
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("LOCAL_PYTEST_STATUS", raising=False)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        assert main([]) == EXIT_OK
        out = capsys.readouterr().out
        assert "shadow_pytest_status=STALE" in out
        assert "shadow_pytest_agreement=UNCOMPARED" in out

    def test_consume_step_replaces_shadow_step(self) -> None:
        """Quality gate consumes pytest.yml signal instead of running tests locally."""
        workflow = yaml.safe_load(
            (Path(__file__).parents[2] / ".github/workflows/ai-pr-quality-gate.yml").read_text(
                encoding="utf-8"
            )
        )
        steps = workflow["jobs"]["run-tests"]["steps"]
        assert not [s for s in steps if "shadow" in s.get("name", "").lower()]
        assert any("resolve pytest signal" in s.get("name", "").lower() for s in steps)
