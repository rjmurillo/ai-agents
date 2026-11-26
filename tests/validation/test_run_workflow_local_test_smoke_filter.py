"""act allowance for plugin-cli-smoke.yml's path filter job.

act's synthetic pull_request payload has no base or head SHA. The filter job
then fails in one of two ways: the base-commit checkout cannot fetch an unpushed
github.sha (git exits 128), or ``cli_smoke_paths.py`` rejects the missing SHAs
(exit 2). These tests pin the allowance to that job, those two steps, and the
two adjacent act lines.
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

_JOB = "[Plugin CLI Smoke/Smoke path filter]"
_OTHER_JOB = "[Plugin CLI Smoke/Trusted-context gate]"
_CHECKOUT = "Checkout the path filter from the base commit"
_DECIDE = "Decide whether the smoke must run"
_EVENT = "pull_request"


def _checkout_failure(job: str = _JOB, step: str = _CHECKOUT) -> str:
    """Lines copied from a real pre-push act log, parameterized."""
    return (
        f"      {job}   ❗  ::error::The process '/usr/bin/git' failed with exit code 128\n"
        f"      {job}   ❌  Failure - Main {step} [28.261404279s]\n"
        f"      {job} exitcode '1': failure\n"
    )


def _decide_failure(job: str = _JOB, step: str = _DECIDE) -> str:
    return (
        f"      {job}   | cli_smoke_paths.py: error: --base and --head are required "
        "for pull_request\n"
        f"      {job}   ❌  Failure - Main {step} [130.202547ms]\n"
        f"      {job} exitcode '2': failure\n"
    )


@pytest.mark.parametrize(
    "text", [_checkout_failure(), _decide_failure()], ids=["checkout", "decide"]
)
def test_hint_matches_both_payload_failures(text: str) -> None:
    hint = w._act_limitation_hint(text, _EVENT)

    assert hint is not None
    assert "plugin-cli-smoke" in hint


@pytest.mark.parametrize(
    "text",
    [
        _checkout_failure(job=_OTHER_JOB),
        _decide_failure(job=_OTHER_JOB),
        _checkout_failure(step="Setup Python"),
        _decide_failure(step="Setup Python"),
        _decide_failure().replace("--base and --head are required", "--base is required"),
        "",
    ],
    ids=[
        "checkout-other-job",
        "decide-other-job",
        "checkout-step",
        "decide-step",
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
    "text", [_checkout_failure(), _decide_failure()], ids=["checkout", "decide"]
)
def test_hint_requires_the_two_lines_to_be_adjacent(text: str) -> None:
    first, second, third = text.splitlines(keepends=True)
    interleaved = f"{first}      {_JOB}   | other output\n{second}{third}"

    assert w._act_limitation_hint(interleaved, _EVENT) is None


def test_hint_rejects_a_failure_line_the_step_echoed() -> None:
    """Step output carries act's `| ` prefix, so it cannot stand in for act's line."""
    forged = (
        f"      {_JOB}   | cli_smoke_paths.py: error: --base and --head are required "
        "for pull_request\n"
        f"      {_JOB}   | ❌  Failure - Main {_DECIDE} [1ms]\n"
    )

    assert w._act_limitation_hint(forged, _EVENT) is None


def test_hint_blocks_when_another_step_also_failed() -> None:
    other = f"      {_OTHER_JOB}   ❌  Failure - Main Check trusted context [3ms]\n"

    assert w._act_limitation_hint(_decide_failure() + other, _EVENT) is None
    assert w._act_limitation_hint(_checkout_failure() + other, _EVENT) is None


def test_a_git_annotation_from_another_job_still_blocks() -> None:
    """The exit 128 annotation is excused for this job's label only."""
    foreign = (
        f"      {_OTHER_JOB}   ❗  ::error::The process '/usr/bin/git' failed with exit code 128\n"
    )

    assert w._act_limitation_hint(_decide_failure() + foreign, _EVENT) is None


def test_the_rule_names_match_plugin_cli_smoke_yml() -> None:
    """The rule quotes the workflow; a rename there must fail here."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["changes"]

    assert f"[{workflow['name']}/{job['name']}]" == _JOB
    steps = {step.get("name"): step for step in job["steps"]}
    assert w._ACT_SMOKE_FILTER_CHECKOUT_STEP in steps
    assert w._ACT_SMOKE_FILTER_DECIDE_STEP in steps
    checkout = steps[w._ACT_SMOKE_FILTER_CHECKOUT_STEP]
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha || github.sha }}"


def test_the_rule_quotes_the_checker_error() -> None:
    source = (REPO_ROOT / "scripts" / "validation" / "cli_smoke_paths.py").read_text(
        encoding="utf-8"
    )

    assert "--base and --head are required for pull_request" in source
