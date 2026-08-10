"""Static-contract tests for bounded pytest-xdist parallelism in pytest.yml.

Issue #4823. Exactly one pytest invocation in this workflow runs on workers:
the "Run pytest" step in job `test`, at `-n auto --dist loadfile`.
Everything else stays serial:

* both branch-coverage pin collection steps, whose 100% gates
  (`tests/workflows/test_pytest_coverage_pins.py`) were measured serially and
  which run five files in seconds, so distribution would only add worker
  startup;
* the Windows path-contract job, whose marker-selected set is small and whose
  runner is the slowest and least parallel-friendly in the matrix.

`auto` is xdist's own "one worker per logical CPU". The workflow states no
number, so a larger runner is spent rather than wasted and nothing has to be
re-tuned when the runner size changes.
`test_main_run_does_not_hard_code_a_worker_count` is the guard on that.

Coverage needs no new step. pytest-cov 7.1.0's `DistMaster.finish()` (verbatim,
`pytest_cov/engine.py`):

    self.cov.stop()
    self.cov.save()
    self.cov = self.combining_cov
    self.cov.load()
    self.cov.combine()
    self.cov.save()

and `combining_cov` is constructed with
`data_file=os.path.abspath(self.cov.config.data_file)`, which is the step's own
`COVERAGE_FILE`. Worker data is therefore already merged into
`artifacts/.coverage.main` before `scripts/ci/combine_pin_coverage.py` reads
it, so that script and its `--main-data` contract are unchanged by this issue.

The local half of this policy (the pre-push gate, the worker-count parser, and
the global-addopts prohibition) lives in
`tests/validation/test_pytest_parallelism_policy.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"

_MAIN_STEP = "Run pytest"
_SERIAL_STEPS = (
    "Pin ai_review_common.verdict coverage collection (REQ-008-07)",
    "Pin REQ-009 module coverage collection (PR #1989 user requirement)",
)
_WINDOWS_JOB = "test-windows-pwsh"
_WINDOWS_STEP = "Run Windows path-contract tests"

_EXPECTED_WORKERS = "auto"
_EXPECTED_DIST = "loadfile"

# Any argv spelling that starts workers or picks a distribution mode.
_PARALLEL_TOKEN = re.compile(r"(?<!\S)(-n|--numprocesses|--dist)(?:[=\s]|$)")


def _job_steps(job: str) -> list[dict[str, Any]]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        workflow: dict[str, Any] = yaml.safe_load(handle)
    return workflow["jobs"][job]["steps"]


def _step(name: str, job: str = "test") -> dict[str, Any]:
    matches = [step for step in _job_steps(job) if step.get("name") == name]
    assert len(matches) == 1, f"expected exactly one step named {name!r}, found {len(matches)}"
    return matches[0]


def _run(name: str, job: str = "test") -> str:
    run = _step(name, job)["run"]
    assert isinstance(run, str), f"step {name!r} has no string 'run' command"
    return run


def test_main_run_uses_every_cpu_over_whole_files() -> None:
    """The one parallel invocation, spelled out.

    `loadfile` sends every test in one file to one worker, which is the
    weakest distribution xdist offers and the point: module-scoped fixtures and
    module state keep behaving the way they do serially.
    """
    tokens = _run(_MAIN_STEP).split()

    assert "-n" in tokens, "main run must pass -n explicitly"
    assert tokens[tokens.index("-n") + 1] == _EXPECTED_WORKERS
    assert "--dist" in tokens, "main run must pin the distribution mode"
    assert tokens[tokens.index("--dist") + 1] == _EXPECTED_DIST


def test_main_run_does_not_hard_code_a_worker_count() -> None:
    """The inverse of the assertion above.

    A regression that swaps `auto` for a number still passes "there is a `-n`"
    while capping a larger runner at whatever the author's machine had. The
    workflow must name no count at all.
    """
    tokens = _run(_MAIN_STEP).split()

    workers = tokens[tokens.index("-n") + 1]

    assert not workers.lstrip("+-").isdigit(), (
        f"worker count must stay runner-relative, got the literal {workers!r}"
    )


def test_main_run_keeps_its_coverage_and_ignore_contract() -> None:
    """Parallelism must not have displaced the flags the pins depend on.

    The pin steps re-run the five files this step ignores, and
    `scripts/ci/combine_pin_coverage.py` reads this step's data file, so
    dropping `--cov` or an `--ignore` while adding `-n` would double-run tests
    and break the combine input at the same time.
    """
    run = _run(_MAIN_STEP)

    assert "--cov " in run or run.rstrip().endswith("--cov")
    assert "--cov-report=" in run
    assert "--cov-branch" not in run
    assert run.count("--ignore=") == 5
    assert "--junitxml=artifacts/pytest-results.xml" in run


def test_pin_collection_steps_stay_serial() -> None:
    """Neither branch-coverage pin may acquire workers.

    Their 100% gates read each step's own data file. Adding workers there would
    buy nothing (five files, seconds) and would put a second combine path in
    front of a gate that must stay exact.
    """
    for name in _SERIAL_STEPS:
        run = _run(name)
        assert _PARALLEL_TOKEN.search(run) is None, (
            f"{name!r} must stay serial, found a parallel flag in: {run!r}"
        )


def test_windows_path_contract_job_stays_serial() -> None:
    run = _run(_WINDOWS_STEP, job=_WINDOWS_JOB)

    assert _PARALLEL_TOKEN.search(run) is None, (
        f"the Windows job must stay serial, found a parallel flag in: {run!r}"
    )
    assert "-m windows_path" in run


def test_the_test_job_has_exactly_one_parallel_step() -> None:
    """A whole-job sweep, so a future pytest step cannot quietly add workers."""
    parallel_steps = [
        step.get("name")
        for step in _job_steps("test")
        if isinstance(step.get("run"), str) and _PARALLEL_TOKEN.search(step["run"])
    ]

    assert parallel_steps == [_MAIN_STEP]


def test_no_explicit_coverage_combine_step_was_added_for_workers() -> None:
    """pytest-cov already merges worker data into this step's COVERAGE_FILE.

    `DistMaster.finish()` calls `combining_cov.combine()` against
    `data_file=os.path.abspath(self.cov.config.data_file)`, so the merge target
    is `artifacts/.coverage.main` itself. A hand-rolled `coverage combine` here
    would re-read already-combined data and could only add failure modes.
    """
    combine_run = _run("Combine coverage data")

    assert "coverage combine" not in combine_run
    assert "scripts/ci/combine_pin_coverage.py" in combine_run
    assert "--main-data artifacts/.coverage.main" in combine_run
