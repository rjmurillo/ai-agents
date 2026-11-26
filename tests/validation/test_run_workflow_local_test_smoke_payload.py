"""act allowance for plugin-cli-smoke.yml's missing pull_request SHAs.

act's synthetic pull_request payload has no base or head SHA. Every job of the
workflow then fails at its base-commit checkout (git exits 128 on an unpushed
github.sha), and, with a pushed commit, the path filter fails in
``cli_smoke_paths.py`` (exit 2). These tests pin the allowance to this
workflow's jobs, those steps, and the two adjacent act lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import run_workflow_local_test as w

_FILTER_JOB = "[Plugin CLI Smoke/Smoke path filter]"
_OTHER_WORKFLOW_JOB = "[Duplicate Code Detection/Python duplication ratchet]"
_DECIDE = "Decide whether the smoke must run"
_EVENT = "pull_request"
_SCRIPTS_STEP = "Checkout trusted scripts from the base commit"
_CHECKOUT_BY_JOB = {
    "[Plugin CLI Smoke/Smoke path filter]": "Checkout the path filter from the base commit",
    "[Plugin CLI Smoke/Trusted-context gate]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/Smoke (codex, ubuntu-latest)]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/Smoke (pi, ubuntu-latest)]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/Smoke (claude hook discovery, ubuntu)]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/CLI Smoke Result]": "Checkout reporter script from the base commit",
}


_SHA = "07136aad753f7ec340165b7c212d353fd65dd42f"
_UNKNOWN_SHA_FATAL = f"fatal: remote error: upload-pack: not our ref {_SHA}"
_MISSING_REF_FATAL = "fatal: couldn't find remote ref refs/heads/no-such-branch"


def _checkout_failure(job: str, step: str, fatal: str | None = _UNKNOWN_SHA_FATAL) -> str:
    """Lines copied from a real pre-push act log, parameterized.

    The fatal line is what git prints for the unpushed ``github.sha`` the
    checkout falls back to. ``fatal=None`` leaves it out.
    """
    fatal_line = f"      {job}   | {fatal}\n" if fatal is not None else ""
    return (
        f"{fatal_line}"
        f"      {job}   ❗  ::error::The process '/usr/bin/git' failed with exit code 128\n"
        f"      {job}   ❌  Failure - Main {step} [28.261404279s]\n"
        f"      {job} exitcode '1': failure\n"
    )


def _decide_failure(job: str = _FILTER_JOB, step: str = _DECIDE) -> str:
    return (
        f"      {job}   | cli_smoke_paths.py: error: --base and --head are required "
        "for pull_request\n"
        f"      {job}   ❌  Failure - Main {step} [130.202547ms]\n"
        f"      {job} exitcode '2': failure\n"
    )


@pytest.mark.parametrize(("job", "step"), sorted(_CHECKOUT_BY_JOB.items()))
def test_hint_matches_the_checkout_failure_of_each_job(job: str, step: str) -> None:
    hint = w._act_limitation_hint(_checkout_failure(job, step), _EVENT)

    assert hint is not None
    assert "plugin-cli-smoke" in hint


def test_hint_matches_the_path_filter_failure() -> None:
    assert w._act_limitation_hint(_decide_failure(), _EVENT) is not None


@pytest.mark.parametrize(
    "text",
    [
        _checkout_failure(_OTHER_WORKFLOW_JOB, "Checkout trusted scripts from the base commit"),
        _checkout_failure(_FILTER_JOB, "Setup Python"),
        _decide_failure(job="[Plugin CLI Smoke/Trusted-context gate]"),
        _decide_failure(job=_OTHER_WORKFLOW_JOB),
        _decide_failure(step="Setup Python"),
        _decide_failure().replace("--base and --head are required", "--base is required"),
        "",
    ],
    ids=[
        "checkout-other-workflow",
        "checkout-other-step",
        "decide-other-plugin-job",
        "decide-other-workflow",
        "decide-other-step",
        "message",
        "empty",
    ],
)
def test_hint_ignores_other_failures(text: str) -> None:
    assert w._act_limitation_hint(text, _EVENT) is None


def test_hint_applies_to_pull_request_runs_only() -> None:
    assert w._act_limitation_hint(_decide_failure(), "workflow_dispatch") is None
    assert w._act_limitation_hint(_decide_failure(), None) is None


@pytest.mark.parametrize(
    "text",
    [_checkout_failure(_FILTER_JOB, _CHECKOUT_BY_JOB[_FILTER_JOB]), _decide_failure()],
    ids=["checkout", "decide"],
)
def test_hint_requires_the_two_lines_to_be_adjacent(text: str) -> None:
    *head, first, second, third = text.splitlines(keepends=True)
    interleaved = f"{''.join(head)}{first}      {_FILTER_JOB}   | other output\n{second}{third}"

    assert w._act_limitation_hint(interleaved, _EVENT) is None


def test_hint_rejects_a_failure_line_the_step_echoed() -> None:
    """Step output carries act's `| ` prefix, so it cannot stand in for act's line."""
    forged = (
        f"      {_FILTER_JOB}   | cli_smoke_paths.py: error: --base and --head are required "
        "for pull_request\n"
        f"      {_FILTER_JOB}   | ❌  Failure - Main {_DECIDE} [1ms]\n"
    )

    assert w._act_limitation_hint(forged, _EVENT) is None


def test_hint_blocks_when_another_step_also_failed() -> None:
    other = f"      {_FILTER_JOB}   ❌  Failure - Main Setup Python [3ms]\n"
    checkout = _checkout_failure(_FILTER_JOB, _CHECKOUT_BY_JOB[_FILTER_JOB])

    assert w._act_limitation_hint(_decide_failure() + other, _EVENT) is None
    assert w._act_limitation_hint(checkout + other, _EVENT) is None


def test_a_git_annotation_from_another_workflow_still_blocks() -> None:
    """The exit 128 annotation is excused for this workflow's labels only."""
    foreign = (
        f"      {_OTHER_WORKFLOW_JOB}   ❗  ::error::The process '/usr/bin/git' "
        "failed with exit code 128\n"
    )

    assert w._act_limitation_hint(_decide_failure() + foreign, _EVENT) is None


def test_the_rule_names_match_plugin_cli_smoke_yml() -> None:
    """The rule quotes the workflow; a rename there must fail here."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml").read_text(encoding="utf-8")
    )
    checkout_steps: set[str] = set()
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            with_block = step.get("with") or {}
            if with_block.get("path") == "trusted-base":
                checkout_steps.add(step["name"])
                assert with_block["ref"] == (
                    "${{ github.event.pull_request.base.sha || github.sha }}"
                )

    assert checkout_steps == set(w._ACT_SMOKE_CHECKOUT_STEPS)
    changes = workflow["jobs"]["changes"]
    assert f"[{workflow['name']}/{changes['name']}]" == _FILTER_JOB
    assert w._ACT_SMOKE_DECIDE_STEP in {step.get("name") for step in changes["steps"]}


def test_the_rule_quotes_the_checker_error() -> None:
    source = (REPO_ROOT / "scripts" / "validation" / "cli_smoke_paths.py").read_text(
        encoding="utf-8"
    )

    assert "--base and --head are required for pull_request" in source


def test_a_same_named_step_from_another_workflow_still_blocks() -> None:
    """Allowed failure lines must carry this workflow's label, not just a step name."""
    foreign = (
        f"      {_OTHER_WORKFLOW_JOB}   \u274c  Failure - Main "
        "Checkout trusted scripts from the base commit [1ms]\n"
    )

    assert w._act_limitation_hint(_decide_failure() + foreign, _EVENT) is None


def test_the_annotation_excuse_needs_the_smoke_rule_not_any_rule() -> None:
    """Another rule matching the run must not excuse a stray smoke git 128 annotation."""
    duplicate = (
        "      [Duplicate Code Detection/Python duplication ratchet]   "
        "| ERROR: git cannot name a fork point with 'origin/master'\n"
        "      [Duplicate Code Detection/Python duplication ratchet]   \u274c  "
        "Failure - Main Check Python duplication against the baseline [2.3s]\n"
    )
    stray = (
        f"      {_FILTER_JOB}   \u2757  ::error::The process '/usr/bin/git' failed with exit "
        "code 128\n"
    )

    assert w._act_limitation_hint(duplicate, _EVENT) is not None
    assert w._act_limitation_hint(duplicate + stray, _EVENT) is None


_FILTER_CHECKOUT = _CHECKOUT_BY_JOB[_FILTER_JOB]
_GATE_JOB = "[Plugin CLI Smoke/Trusted-context gate]"


def test_a_nonexistent_explicit_ref_still_blocks() -> None:
    """Only git's unknown-SHA fatal vouches for the fallback; a missing ref is a defect."""
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=_MISSING_REF_FATAL)

    assert w._act_limitation_hint(text, _EVENT) is None


def test_a_checkout_failure_without_a_fatal_line_still_blocks() -> None:
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=None)

    assert w._act_limitation_hint(text, _EVENT) is None


def test_one_nonexistent_ref_blocks_beside_missing_sha_failures() -> None:
    explained = _checkout_failure(_GATE_JOB, _SCRIPTS_STEP)
    broken = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=_MISSING_REF_FATAL)

    assert w._act_limitation_hint(explained, _EVENT) is not None
    assert w._act_limitation_hint(explained + broken, _EVENT) is None


def test_the_unknown_sha_fatal_must_come_from_the_failing_job() -> None:
    """Another job's fatal line cannot vouch for this job's checkout failure."""
    other_job_fatal = _checkout_failure(_GATE_JOB, _SCRIPTS_STEP)
    unexplained = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=None)

    assert w._act_limitation_hint(other_job_fatal + unexplained, _EVENT) is None


def test_an_unknown_sha_fatal_from_another_workflow_does_not_vouch() -> None:
    foreign = f"      {_OTHER_WORKFLOW_JOB}   | {_UNKNOWN_SHA_FATAL}\n"
    unexplained = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=None)

    assert w._act_limitation_hint(foreign + unexplained, _EVENT) is None


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

    assert w._act_limitation_hint(text, _EVENT) is None


def test_any_other_fatal_line_from_the_workflow_blocks() -> None:
    """A checkout that also died on a different fatal cannot ride on the fallback."""
    extra = f"      {_GATE_JOB}   | {_MISSING_REF_FATAL}\n"
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT) + extra

    assert w._act_limitation_hint(text, _EVENT) is None


def test_hint_accepts_the_width_padding_act_adds_to_job_labels() -> None:
    """act pads every label to the widest job in the run, inside the brackets."""
    padded_filter = "[Plugin CLI Smoke/Smoke path filter ]"
    padded_gate = "[Plugin CLI Smoke/Trusted-context gate   ]"

    assert w._act_limitation_hint(_decide_failure(job=padded_filter), _EVENT) is not None
    checkout = _checkout_failure(padded_filter, _FILTER_CHECKOUT) + _checkout_failure(
        padded_gate, _SCRIPTS_STEP
    )
    assert w._act_limitation_hint(checkout, _EVENT) is not None


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

    assert w._act_limitation_hint(text, _EVENT) is None


def test_a_unicode_line_break_cannot_forge_a_vouching_fatal_line() -> None:
    """Lines split on newline only, as the regexes do, so U+2028 cannot start a new line."""
    unexplained = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=None)
    forged = f"      {_GATE_JOB}   | echo\u2028      {_FILTER_JOB}   | {_UNKNOWN_SHA_FATAL}\n"

    assert w._act_limitation_hint(unexplained + forged, _EVENT) is None


def test_hint_accepts_git_s_three_fold_fetch_retry() -> None:
    """actions/checkout retries the fetch, so a real log repeats the fatal line."""
    fatal = f"      {_FILTER_JOB}   | {_UNKNOWN_SHA_FATAL}\n"
    text = fatal * 2 + _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT)

    assert w._act_limitation_hint(text, _EVENT) is not None


def test_no_checkout_in_the_workflow_names_another_repository() -> None:
    """git prints the same unknown-SHA line for a foreign repository, so none may be set."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml").read_text(encoding="utf-8")
    )
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

    assert w._act_limitation_hint(explained, _EVENT) is not None
    assert w._act_limitation_hint(explained + other_job_failure, _EVENT) is None


def test_a_stray_git_annotation_beside_a_path_filter_failure_still_blocks() -> None:
    """The annotation excuse covers a job whose checkout failure is explained, no other."""
    stray = (
        f"      {_FILTER_JOB}   ❗  ::error::The process '/usr/bin/git' failed with exit code 128\n"
    )

    assert w._act_limitation_hint(_decide_failure(), _EVENT) is not None
    assert w._act_limitation_hint(_decide_failure() + stray, _EVENT) is None


def test_the_annotation_excuse_applies_to_pull_request_runs_only() -> None:
    text = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT)

    assert w._unexplained_error_annotations(text, _EVENT) == []
    assert w._unexplained_error_annotations(text, None) != []
    assert w._unexplained_error_annotations(text, "workflow_dispatch") != []


def test_the_allowed_checkout_steps_are_actions_checkout_steps() -> None:
    """The allowance trusts log text, so the steps it names must be the checkout action."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml").read_text(encoding="utf-8")
    )
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
    fatal = f"      {_FILTER_JOB}   | {_UNKNOWN_SHA_FATAL}\n"
    annotation = (
        f"      {_FILTER_JOB}   \u2757  ::error::The process '/usr/bin/git' failed with exit "
        "code 128\n"
    )

    assert w._act_limitation_hint(explained, _EVENT) is not None
    extra_words = f"{fatal}{annotation}{padded} and more [1ms]\n"
    no_duration = f"{fatal}{annotation}{padded}\n"
    assert w._act_limitation_hint(extra_words, _EVENT) is None
    assert w._act_limitation_hint(no_duration, _EVENT) is None


def test_decide_error_evidence_does_not_vouch_for_a_checkout_failure() -> None:
    """The two kinds of evidence are separate: each failure needs its own."""
    error_line = (
        f"      {_FILTER_JOB}   | cli_smoke_paths.py: error: --base and --head are required "
        "for pull_request\n"
    )
    checkout_without_fatal = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=None)

    assert w._act_limitation_hint(error_line + checkout_without_fatal, _EVENT) is None


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

    assert w._act_limitation_hint(text, _EVENT) is not None


def test_a_long_adversarial_failure_line_is_rejected_quickly() -> None:
    """The failure-line regex must stay linear on a step that prints a huge line."""
    import time

    hostile = f"      {_FILTER_JOB}   \u274c  Failure - Main {_DECIDE}" + " [" * 100_000 + "\n"
    start = time.perf_counter()
    hint = w._act_limitation_hint(_decide_failure() + hostile, _EVENT)

    assert hint is None
    assert time.perf_counter() - start < 2.0
