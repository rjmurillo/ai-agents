"""Static-contract tests for the pytest coverage-pin split in pytest.yml, job `test`.

Two pin *collection* steps re-run five owned files; "Run pytest" must
--ignore all five and stay statement-only (no --cov-branch), and each
collection step owns a disjoint subset with its own COVERAGE_FILE. Each
collection step collects BROAD branch coverage (bare --cov, not a narrow
module target): those five files exercise other modules incidentally, and a
narrow --cov target would mean pytest-cov never measures those other modules
there at all, so no incidental coverage could ever reach the combined
artifacts/coverage.xml.

Each collection step is immediately followed by its own "Enforce ... at 100%"
step, which runs `coverage report --data-file=<collection's COVERAGE_FILE>
--include=<pinned module path(s)> --fail-under=100` directly against that
collection step's raw data file. `--include` filters the *report* only, so
the incidental modules a collection step also measured cannot move the
pinned module's own percentage in either direction: the isolated 100% branch
gate on the narrow pinned module survives exactly, even though collection
itself is broad. combine_pin_coverage.py's own tests
(tests/ci/test_combine_pin_coverage.py) prove the CLI-level isolation
directly; this module proves the workflow wiring matches that design.

"Combine coverage data" runs scripts/ci/combine_pin_coverage.py to merge the
three raw data files (main + both collection steps) and then `coverage xml`,
after both collection and both enforce steps and before upload. It does not
gate anything itself; it only projects and unions.

The main run stays statement-only on purpose: measured, turning on
--cov-branch for that ~24k-test partition costs +27.02s wall (438.91s ->
465.93s, +6.2%) for a number this step never reports, and produces data that
cannot combine with the pins' branch data through a bare `coverage combine`
anyway (`CoverageData.update()` refuses to mix arc rows with line rows). Do
not "fix" a future regression here by adding --cov-branch to the main run.
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
_REQ009_TARGETS = (
    ".claude/skills/github/scripts/pr/wait_for_unresolved_zero.py",
    ".claude/skills/session-end/scripts/rework_warning.py",
)

_COMBINE_STEP = "Combine coverage data"
_UPLOAD_STEP = "Upload test results"
_HELPER_SCRIPT = "scripts/ci/combine_pin_coverage.py"

_COLLECTION_STEPS = (_VERDICT_COLLECT, _REQ009_COLLECT)
_GATE_STEPS = (_VERDICT_GATE, _REQ009_GATE)

# Runs whenever "Run pytest" actually executed (steps.run-pytest.outcome is
# not 'skipped'), whether it then passed or failed, but not when the job was
# cancelled. Referencing cancelled() drops GitHub's implicit success()-only
# default for a bare boolean `if:` without re-adding one, so this reads the
# main step's own outcome directly rather than the job's aggregate status: a
# checkout or setup step failing before "Run pytest" ever runs leaves
# steps.run-pytest.outcome == 'skipped', and this condition is false then too.
_RUN_AFTER_MAIN_EXECUTED = (
    "steps.should-run.outputs.skip != 'true' && "
    "steps.run-pytest.outcome != 'skipped' && "
    "!cancelled()"
)


def _run_after_collection_executed(collect_step_id: str) -> str:
    """The `if:` an enforce step must carry: gated on its own collection
    step's outcome (not the main run's), so it still runs, and still
    enforces the gate, if that one collection step's own tests failed
    outright. Same cancelled()-based reasoning as `_RUN_AFTER_MAIN_EXECUTED`."""
    return (
        "steps.should-run.outputs.skip != 'true' && "
        f"steps.{collect_step_id}.outcome != 'skipped' && "
        "!cancelled()"
    )


# The five files the two pin collection steps own; each is ignored by main,
# run by exactly one collection step.
_OWNED_FILES = (
    "tests/test_ai_review.py",
    "tests/test_verdict.py",
    "tests/test_quality_gate.py",
    "tests/skills/github/test_wait_for_unresolved_zero.py",
    "tests/skills/session-end/test_rework_warning.py",
)

_IGNORE_PATTERN = re.compile(r"--ignore=(\S+)")


def _test_job_steps() -> list[dict[str, Any]]:
    """Return the `test` job's steps; a malformed tracked workflow fails loudly."""
    with _WORKFLOW.open(encoding="utf-8") as handle:
        workflow: dict[str, Any] = yaml.safe_load(handle)
    return workflow["jobs"]["test"]["steps"]


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
    """ "Run pytest" is given `id: run-pytest` (the collection steps and
    combine gate on its outcome) and must never carry --cov-branch: see
    module docstring for the +27.02s / +6.2% measurement behind keeping it
    statement-only."""
    step = _step(_MAIN_STEP)
    assert step.get("id") == _MAIN_STEP_ID

    main_run = _run(_MAIN_STEP)
    assert "--cov-branch" not in main_run, "main run must stay statement-only, not branch, coverage"
    assert "--cov " in main_run or main_run.rstrip().endswith("--cov"), (
        "main run must still collect --cov"
    )
    assert "--cov-report=" in main_run, (
        "main run must suppress its own xml report; combine writes it"
    )


def test_main_run_ignores_exactly_the_pin_owned_files() -> None:
    main_run = _run(_MAIN_STEP)
    ignored = set(_IGNORE_PATTERN.findall(main_run))
    assert ignored == set(_OWNED_FILES)


def test_pin_collection_steps_collect_broad_branch_coverage_with_no_inline_fail_under() -> None:
    """Each owned file goes to exactly one collection step; both collection
    steps keep --cov-branch (their gate needs arc data) but drop the narrow
    --cov=<module> target and any --cov-fail-under: those moved to the
    separate "Enforce ... at 100%" steps. --cov-report= keeps the terminal
    report suppressed, same as the main run."""
    collection_runs = {name: _run(name) for name in _COLLECTION_STEPS}
    for owned_file in _OWNED_FILES:
        claims = sum(owned_file in run for run in collection_runs.values())
        assert claims == 1, (
            f"{owned_file!r} must appear in exactly one collection step, found {claims}"
        )

    coverage_files = [_coverage_file(name) for name in (_MAIN_STEP, *_COLLECTION_STEPS)]
    assert len(set(coverage_files)) == 3, f"expected 3 distinct COVERAGE_FILE, got {coverage_files}"

    for name, run in collection_runs.items():
        assert "--cov-branch" in run, f"{name!r} must keep --cov-branch"
        assert "--cov-report=" in run, f"{name!r} must suppress its own terminal report"
        assert "--cov-fail-under" not in run, (
            f"{name!r} must not gate inline; the gate lives in its Enforce step"
        )
        assert "--cov=" not in run, (
            f"{name!r} must collect BROAD coverage (bare --cov), not a narrow module "
            "target, so incidental modules are measured too"
        )
        assert re.search(r"--cov(\s|$)", run), f"{name!r} must still pass bare --cov"


def test_enforce_steps_gate_exactly_the_pinned_module_at_100_percent() -> None:
    """Each Enforce step runs `coverage report` (not pytest) directly against
    its own collection step's COVERAGE_FILE, --include'd down to exactly the
    pinned module path(s), at --fail-under=100. This is the isolated 100%
    branch gate the design preserves even though collection itself is broad."""
    verdict_coverage_file = _coverage_file(_VERDICT_COLLECT)
    req009_coverage_file = _coverage_file(_REQ009_COLLECT)

    verdict_gate_run = _run(_VERDICT_GATE)
    assert "pytest" not in verdict_gate_run, "the gate step must not re-run tests"
    assert "coverage report" in verdict_gate_run
    assert f"--data-file={verdict_coverage_file}" in verdict_gate_run
    assert f"--include={_VERDICT_TARGET}" in verdict_gate_run, (
        "verdict gate must --include exactly scripts/ai_review_common/verdict.py, "
        "no more and no less"
    )
    assert "--fail-under=100" in verdict_gate_run

    req009_gate_run = _run(_REQ009_GATE)
    assert "pytest" not in req009_gate_run, "the gate step must not re-run tests"
    assert "coverage report" in req009_gate_run
    assert f"--data-file={req009_coverage_file}" in req009_gate_run
    assert f"--include={','.join(_REQ009_TARGETS)}" in req009_gate_run, (
        "REQ-009 gate must --include exactly the two pinned module paths, "
        "comma-joined, no more and no less"
    )
    assert "--fail-under=100" in req009_gate_run


def test_enforce_steps_gate_on_their_own_collection_step_not_the_main_run() -> None:
    """Each Enforce step's `if:` reads its own collection step's outcome, not
    "Run pytest"'s: it must still enforce the gate when the collection step's
    own tests failed, and gating on the wrong step would skip enforcement
    whenever only the *other* pin's tests failed while this collection step
    still produced data."""
    assert _step(_VERDICT_GATE)["if"] == _run_after_collection_executed(_VERDICT_COLLECT_ID)
    assert _step(_REQ009_GATE)["if"] == _run_after_collection_executed(_REQ009_COLLECT_ID)


def test_collection_and_combine_run_after_main_executed_but_not_before_or_cancelled() -> None:
    """Both collection steps and the combine step share the same gate: they
    run whenever "Run pytest" actually executed, pass or fail, but never when
    it was skipped by an earlier checkout/setup failure and never on
    cancellation."""
    for name in (*_COLLECTION_STEPS, _COMBINE_STEP):
        assert _step(name)["if"] == _RUN_AFTER_MAIN_EXECUTED, (
            f"{name!r} must gate on the main step's own outcome, got {_step(name)['if']!r}"
        )


def test_verdict_collection_has_the_id_its_own_gate_step_depends_on() -> None:
    assert _step(_VERDICT_COLLECT).get("id") == _VERDICT_COLLECT_ID


def test_req009_collection_has_the_id_its_own_gate_step_depends_on() -> None:
    assert _step(_REQ009_COLLECT).get("id") == _REQ009_COLLECT_ID


def test_step_ordering_is_collect_then_gate_then_combine_before_upload() -> None:
    """Each collection step precedes its own gate step; both gate steps
    precede combine; combine precedes upload."""
    verdict_collect_index = _step_index(_VERDICT_COLLECT)
    verdict_gate_index = _step_index(_VERDICT_GATE)
    req009_collect_index = _step_index(_REQ009_COLLECT)
    req009_gate_index = _step_index(_REQ009_GATE)
    combine_index = _step_index(_COMBINE_STEP)
    upload_index = _step_index(_UPLOAD_STEP)

    assert verdict_gate_index > verdict_collect_index, (
        "verdict gate must run after verdict collection"
    )
    assert req009_gate_index > req009_collect_index, (
        "REQ-009 gate must run after REQ-009 collection"
    )
    for gate_index in (verdict_gate_index, req009_gate_index):
        assert combine_index > gate_index, "combine must run after both gate steps"
    assert combine_index < upload_index, "combine must run before the upload step"


def test_combine_step_runs_after_pins_before_upload_and_writes_coverage_xml() -> None:
    """Combine runs after both collection (and gate) steps, before upload,
    invokes the Python helper (not a bare `coverage combine`) with the three
    COVERAGE_FILE paths, and generates artifacts/coverage.xml from the
    helper's output."""
    combine_index = _step_index(_COMBINE_STEP)
    assert combine_index > _step_index(_VERDICT_COLLECT), (
        "combine must run after the verdict collection step"
    )
    assert combine_index > _step_index(_REQ009_COLLECT), (
        "combine must run after the REQ-009 collection step"
    )
    assert combine_index < _step_index(_UPLOAD_STEP), "combine must run before the upload step"

    run = _run(_COMBINE_STEP)
    assert _HELPER_SCRIPT in run, (
        "combine must delegate to the Python helper, not inline coverage combine logic"
    )
    assert "coverage combine" not in run, (
        "YAML must stay orchestration-only; no bare `coverage combine` call"
    )

    main_coverage_file = _coverage_file(_MAIN_STEP)
    verdict_coverage_file = _coverage_file(_VERDICT_COLLECT)
    req009_coverage_file = _coverage_file(_REQ009_COLLECT)
    assert f"--main-data {main_coverage_file}" in run
    assert f"--pin-data {verdict_coverage_file}" in run
    assert f"--pin-data {req009_coverage_file}" in run

    output_match = re.search(r"--output-data\s+(\S+)", run)
    assert output_match is not None, "combine step must pass --output-data to the helper"
    output_data = output_match.group(1)

    assert f"--data-file={output_data}" in run, (
        "coverage xml must read the helper's combined output"
    )
    assert "coverage xml" in run
    assert "-o artifacts/coverage.xml" in run


def test_combine_step_has_no_shell_branching_or_counting() -> None:
    """ADR-006: YAML orchestration only. The combine step's run block is two
    plain commands (helper invocation, then `coverage xml`); no shell `if`,
    loop, or file-counting logic belongs here now that combine_pin_coverage.py
    owns the validation logic."""
    run = _run(_COMBINE_STEP)
    forbidden_tokens = (" if ", " if[", "\nif ", "for ", "while ", "$(", "`")
    for token in forbidden_tokens:
        assert token not in run, (
            f"combine step run block must not contain shell logic token {token!r}"
        )
