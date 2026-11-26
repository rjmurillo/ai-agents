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


def _checkout_failure(job: str, step: str) -> str:
    """Lines copied from a real pre-push act log, parameterized."""
    return (
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
    first, second, third = text.splitlines(keepends=True)
    interleaved = f"{first}      {_FILTER_JOB}   | other output\n{second}{third}"

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
