"""Static-contract tests for the pytest coverage-pin split in pytest.yml.

Issue #4854: the test job is now a five-entry matrix. Pin collection and
enforcement steps run only in the bulk partition. The combine step moves to a
separate coverage job that merges all partition data.

Two pin *collection* steps re-run four owned files in the bulk leg; the shared
"Run pytest" step in bulk --ignores all four and stays statement-only (no
--cov-branch). Each collection step owns a disjoint subset with its own
COVERAGE_FILE. Each collection step collects BROAD branch coverage (bare
--cov, not a narrow module target).

Each collection step is immediately followed by its own "Enforce ... at 100%"
step, which runs `coverage report --data-file=<collection's COVERAGE_FILE>
--include=<pinned module path(s)> --fail-under=100`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"

_MAIN_STEP = "Run pytest"
_MAIN_STEP_ID = "run-pytest"

_VERDICT_COLLECT = "Pin ai_review_common.verdict coverage collection (REQ-008-07)"
_VERDICT_COLLECT_ID = "pin-verdict-collect"
_VERDICT_GATE = "Enforce ai_review_common.verdict coverage at 100% (REQ-008-07)"
_VERDICT_TARGET = "scripts/ai_review_common/verdict.py"

_REQ009_COLLECT = "Pin REQ-009 module coverage collection (PR #1989 user requirement)"
_REQ009_COLLECT_ID = "pin-req009-collect"
_REQ009_GATE = "Enforce REQ-009 module coverage at 100% (PR #1989 user requirement)"
_REQ009_TARGETS = (".claude/skills/github/scripts/pr/wait_for_unresolved_zero.py",)

_UPLOAD_STEP = "Upload test results"

_COLLECTION_STEPS = (_VERDICT_COLLECT, _REQ009_COLLECT)
_GATE_STEPS = (_VERDICT_GATE, _REQ009_GATE)

_RUN_AFTER_MAIN_EXECUTED = (
    "matrix.partition == 'bulk' && steps.run-pytest.outcome != 'skipped' && !cancelled()"
)


def _run_after_collection_executed(collect_step_id: str) -> str:
    return (
        f"steps.{collect_step_id}.outcome != 'skipped' && !cancelled()"
    )


# The four files the two pin collection steps own.
_OWNED_FILES = (
    "tests/test_ai_review.py",
    "tests/test_verdict.py",
    "tests/test_quality_gate.py",
    "tests/skills/github/test_wait_for_unresolved_zero.py",
)

_IGNORE_PATTERN = re.compile(r"--ignore=(\S+)")


def _load_workflow() -> dict[str, Any]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _test_job_steps() -> list[dict[str, Any]]:
    return _load_workflow()["jobs"]["test"]["steps"]


def _step_index(name: str) -> int:
    steps = _test_job_steps()
    matches = [index for index, step in enumerate(steps) if step.get("name") == name]
    assert len(matches) == 1, f"expected exactly one step named {name!r}, found {len(matches)}"
    return matches[0]


def _step(name: str) -> dict[str, Any]:
    return _test_job_steps()[_step_index(name)]


def _run(name: str) -> str:
    run = _step(name)["run"]
    assert isinstance(run, str), f"step {name!r} has no string 'run' command"
    return run


def _coverage_file(step_name: str) -> str:
    env = _step(step_name).get("env")
    assert isinstance(env, dict), f"step {step_name!r} has no env mapping"
    coverage_file = env.get("COVERAGE_FILE")
    assert isinstance(coverage_file, str), f"step {step_name!r} has no COVERAGE_FILE"
    return coverage_file


def test_main_run_has_id_and_stays_statement_only() -> None:
    step = _step(_MAIN_STEP)
    assert step.get("id") == _MAIN_STEP_ID

    main_run = _run(_MAIN_STEP)
    assert "--cov-branch" not in main_run
    assert "--cov" in main_run
    assert "--cov-report=" in main_run


def test_pin_collection_steps_only_in_bulk_partition() -> None:
    """Pin steps carry a matrix.partition == 'bulk' condition."""
    for name in _COLLECTION_STEPS:
        condition = _step(name).get("if", "")
        assert "matrix.partition == 'bulk'" in condition


def test_pin_collection_steps_collect_broad_branch_coverage() -> None:
    collection_runs = {name: _run(name) for name in _COLLECTION_STEPS}
    for owned_file in _OWNED_FILES:
        claims = sum(owned_file in run for run in collection_runs.values())
        assert claims == 1, f"{owned_file!r} in {claims} collection steps, expected 1"

    for _name, run in collection_runs.items():
        assert "--cov-branch" in run
        assert "--cov-report=" in run
        assert "--cov-fail-under" not in run
        assert "--cov=" not in run
        assert re.search(r"--cov(\s|$)", run)


def test_enforce_steps_gate_exactly_the_pinned_module_at_100_percent() -> None:
    verdict_coverage_file = _coverage_file(_VERDICT_COLLECT)
    req009_coverage_file = _coverage_file(_REQ009_COLLECT)

    verdict_gate_run = _run(_VERDICT_GATE)
    assert "coverage report" in verdict_gate_run
    assert f"--data-file={verdict_coverage_file}" in verdict_gate_run
    assert f"--include={_VERDICT_TARGET}" in verdict_gate_run
    assert "--fail-under=100" in verdict_gate_run

    req009_gate_run = _run(_REQ009_GATE)
    assert "coverage report" in req009_gate_run
    assert f"--data-file={req009_coverage_file}" in req009_gate_run
    assert f"--include={','.join(_REQ009_TARGETS)}" in req009_gate_run
    assert "--fail-under=100" in req009_gate_run


def test_enforce_steps_gate_on_their_own_collection_step() -> None:
    assert _step(_VERDICT_GATE)["if"] == _run_after_collection_executed(_VERDICT_COLLECT_ID)
    assert _step(_REQ009_GATE)["if"] == _run_after_collection_executed(_REQ009_COLLECT_ID)


def test_collection_steps_run_after_main_executed() -> None:
    for name in _COLLECTION_STEPS:
        assert _step(name).get("if") == _RUN_AFTER_MAIN_EXECUTED


def test_verdict_collection_has_correct_id() -> None:
    assert _step(_VERDICT_COLLECT).get("id") == _VERDICT_COLLECT_ID


def test_req009_collection_has_correct_id() -> None:
    assert _step(_REQ009_COLLECT).get("id") == _REQ009_COLLECT_ID


def test_step_ordering_is_collect_then_gate_before_upload() -> None:
    verdict_collect_index = _step_index(_VERDICT_COLLECT)
    verdict_gate_index = _step_index(_VERDICT_GATE)
    req009_collect_index = _step_index(_REQ009_COLLECT)
    req009_gate_index = _step_index(_REQ009_GATE)
    upload_index = _step_index(_UPLOAD_STEP)

    assert verdict_gate_index > verdict_collect_index
    assert req009_gate_index > req009_collect_index
    assert upload_index > verdict_gate_index
    assert upload_index > req009_gate_index
