"""Evidence rules for the plugin-cli-smoke.yml act payload allowance.

The allowance in ``run_workflow_local_test.py`` excuses a failure only when the
log carries git's unknown-SHA fatal line from the failing job. These tests pin
that evidence rule, the reporter-job skip, and the shape of the failure line.
The hint-matching tests live in ``test_run_workflow_local_test_smoke_payload.py``.
"""

from __future__ import annotations

import pytest
import yaml

from scripts.validation import run_workflow_local_test as w
from tests.lib.act_smoke_payload import (
    _DECIDE,
    _EVENT,
    _FILTER_CHECKOUT,
    _FILTER_FATAL,
    _FILTER_JOB,
    _GATE_JOB,
    _MISSING_REF_FATAL,
    _OTHER_WORKFLOW_JOB,
    _SCRIPTS_STEP,
    _SHA,
    _UNEXPLAINED,
    _UNKNOWN_SHA_FATAL,
    REPO_ROOT,
    _checkout_failure,
    _decide_error,
    _decide_failure,
    _git_annotation,
    _hint,
    _workflow,
)


def test_a_nonexistent_explicit_ref_still_blocks() -> None:
    """Only git's unknown-SHA fatal vouches for the fallback; a missing ref is a defect."""
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=_MISSING_REF_FATAL)

    assert _hint(text) is None


def test_a_checkout_failure_without_a_fatal_line_still_blocks() -> None:
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=None)

    assert _hint(text) is None


def test_one_nonexistent_ref_blocks_beside_missing_sha_failures() -> None:
    explained = _checkout_failure(_GATE_JOB, _SCRIPTS_STEP)
    broken = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=_MISSING_REF_FATAL)

    assert _hint(explained) is not None
    assert _hint(explained + broken) is None


def test_the_unknown_sha_fatal_must_come_from_the_failing_job() -> None:
    """Another job's fatal line cannot vouch for this job's checkout failure."""
    other_job_fatal = _checkout_failure(_GATE_JOB, _SCRIPTS_STEP)

    assert _hint(other_job_fatal + _UNEXPLAINED) is None


def test_an_unknown_sha_fatal_from_another_workflow_does_not_vouch() -> None:
    foreign = f"      {_OTHER_WORKFLOW_JOB}   | {_UNKNOWN_SHA_FATAL}\n"

    assert _hint(foreign + _UNEXPLAINED) is None


@pytest.mark.parametrize(
    "fatal",
    [
        "fatal: remote error: upload-pack: not our ref 07136aa",
        "fatal: remote error: upload-pack: not our ref refs/heads/no-such-branch",
        f"fatal: remote error: upload-pack: not our ref {_SHA.upper()}",
        f"fatal: remote error: upload-pack: not our ref {_SHA} extra",
        "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
    ],
    ids=["short-sha", "branch-name", "uppercase", "trailing-text", "auth"],
)
def test_only_a_full_sha_unknown_ref_fatal_vouches(fatal: str) -> None:
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=fatal)

    assert _hint(text) is None


def test_any_other_fatal_line_from_the_workflow_blocks() -> None:
    """A checkout that also died on a different fatal cannot ride on the fallback."""
    extra = f"      {_GATE_JOB}   | {_MISSING_REF_FATAL}\n"
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT) + extra

    assert _hint(text) is None


def test_hint_accepts_the_width_padding_act_adds_to_job_labels() -> None:
    """act pads every label to the widest job in the run, inside the brackets."""
    padded_filter = "[Plugin CLI Smoke/Smoke path filter ]"
    padded_gate = "[Plugin CLI Smoke/Trusted-context gate   ]"

    assert _hint(_decide_failure(job=padded_filter)) is not None
    checkout = _checkout_failure(padded_filter, _FILTER_CHECKOUT) + _checkout_failure(
        padded_gate, _SCRIPTS_STEP
    )
    assert _hint(checkout) is not None


def test_the_reporter_job_is_skipped_by_the_full_act_stage_only() -> None:
    """smoke-result reports the path filter's failure, so it can only fail under act."""
    wf = ".github/workflows/plugin-cli-smoke.yml"
    full: list[str] = []
    dry: list[str] = []

    full_jobs = w._act_job_filters(REPO_ROOT, wf, full, full_stage=True)
    dry_jobs = w._act_job_filters(REPO_ROOT, wf, dry)

    assert ["-j", "smoke-result"] not in full_jobs
    assert ["-j", "changes"] in full_jobs
    assert any("smoke-result" in warning and "skipped" in warning for warning in full)
    assert ["-j", "smoke-result"] in dry_jobs
    assert not any("smoke-result" in warning for warning in dry)


def test_other_workflows_keep_every_job_in_the_full_act_stage() -> None:
    warnings: list[str] = []

    jobs = w._act_job_filters(
        REPO_ROOT, ".github/workflows/pr-maintenance.yml", warnings, full_stage=True
    )

    assert jobs == [["-j", "discover-prs"], ["-j", "summarize"]]
    assert not any("reporter" in warning or "synthetic" in warning for warning in warnings)


def test_the_reporter_table_names_jobs_that_exist() -> None:
    """A rename in the workflow must fail here, not silently re-enable the job."""
    for wf, reporters in w._ACT_REPORTER_JOBS.items():
        jobs = yaml.safe_load((REPO_ROOT / wf).read_text(encoding="utf-8"))["jobs"]
        assert set(reporters) <= set(jobs), wf


def test_a_failure_line_with_extra_words_in_the_step_name_still_blocks() -> None:
    """Step names match exactly; a step named like an allowed one plus text is another step."""
    text = _decide_failure(step=f"{_DECIDE} and then something else")

    assert _hint(text) is None


def test_a_unicode_line_break_cannot_forge_a_vouching_fatal_line() -> None:
    """Lines split on newline only, as the regexes do, so U+2028 cannot start a new line."""
    forged = f"      {_GATE_JOB}   | echo\u2028{_FILTER_FATAL}"

    assert _hint(_UNEXPLAINED + forged) is None


def test_hint_accepts_git_s_three_fold_fetch_retry() -> None:
    """actions/checkout retries the fetch, so a real log repeats the fatal line."""
    text = _FILTER_FATAL * 2 + _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT)

    assert _hint(text) is not None


def test_no_checkout_in_the_workflow_names_another_repository() -> None:
    """git prints the same unknown-SHA line for a foreign repository, so none may be set."""
    workflow = _workflow()
    checkouts = [
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]

    assert checkouts
    for step in checkouts:
        assert "repository" not in (step.get("with") or {}), step.get("name")


def test_the_path_filter_failure_needs_its_own_jobs_error_line() -> None:
    """Another job's `--base and --head` error cannot excuse this job's Decide failure."""
    explained = _decide_failure()
    other_job_failure = f"      {_GATE_JOB}   ❌  Failure - Main {_DECIDE} [1ms]\n"

    assert _hint(explained) is not None
    assert _hint(explained + other_job_failure) is None


def test_a_stray_git_annotation_beside_a_path_filter_failure_still_blocks() -> None:
    """The annotation excuse covers a job whose checkout failure is explained, no other."""
    assert _hint(_decide_failure()) is not None
    assert _hint(_decide_failure() + _git_annotation(_FILTER_JOB)) is None


def test_the_annotation_excuse_applies_to_pull_request_runs_only() -> None:
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT)

    assert w._unexplained_error_annotations(text, _EVENT) == []
    assert w._unexplained_error_annotations(text, None) != []
    assert w._unexplained_error_annotations(text, "workflow_dispatch") != []


def test_the_allowed_checkout_steps_are_actions_checkout_steps() -> None:
    """The allowance trusts log text, so the steps it names must be the checkout action."""
    workflow = _workflow()
    steps = [
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("name") in w._ACT_SMOKE_CHECKOUT_STEPS
    ]

    assert {step["name"] for step in steps} == set(w._ACT_SMOKE_CHECKOUT_STEPS)
    assert len(steps) == 6  # four jobs share one step name; the filter and reporter have their own
    for step in steps:
        assert str(step.get("uses", "")).startswith("actions/checkout@"), step["name"]
        assert "run" not in step, step["name"]


def test_a_failure_line_carrying_extra_words_or_no_duration_blocks() -> None:
    padded = f"      {_FILTER_JOB}   \u274c  Failure - Main {_FILTER_CHECKOUT}"
    explained = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT)
    head = _FILTER_FATAL + _git_annotation(_FILTER_JOB)

    assert _hint(explained) is not None
    extra_words = f"{head}{padded} and more [1ms]\n"
    no_duration = f"{head}{padded}\n"
    assert _hint(extra_words) is None
    assert _hint(no_duration) is None


def test_decide_error_evidence_does_not_vouch_for_a_checkout_failure() -> None:
    """The two kinds of evidence are separate: each failure needs its own."""
    assert _hint(_decide_error(_FILTER_JOB) + _UNEXPLAINED) is None


def test_the_full_act_stage_skips_reporters_and_the_dry_run_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reporter skip only works if the stages pass the flag down."""
    calls: dict[str, dict[str, object]] = {}

    def fake_stage(stage: str, *args: object, **kwargs: object) -> str:
        calls[stage] = kwargs
        return stage

    monkeypatch.setattr(w, "_run_act_stage", fake_stage)

    w._act_full_stage([], REPO_ROOT)
    w._act_dryrun_stage([], REPO_ROOT)

    assert calls["gh act (full)"].get("full_stage") is True
    assert not calls["gh act -n"].get("full_stage")


@pytest.mark.parametrize(
    "duration", ["1ms", "37.28554875s", "144.507667ms", "1m5.5s", "2h3m4s", "12\u00b5s"]
)
def test_hint_accepts_every_go_duration_shape_act_prints(duration: str) -> None:
    text = _decide_failure().replace("[130.202547ms]", f"[{duration}]")

    assert _hint(text) is not None


def test_a_long_adversarial_failure_line_is_rejected_quickly() -> None:
    """The failure-line regex must stay linear on a step that prints a huge line."""
    import time

    hostile = f"      {_FILTER_JOB}   \u274c  Failure - Main {_DECIDE}" + " [" * 100_000 + "\n"
    start = time.perf_counter()
    hint = _hint(_decide_failure() + hostile)

    assert hint is None
    assert time.perf_counter() - start < 2.0
