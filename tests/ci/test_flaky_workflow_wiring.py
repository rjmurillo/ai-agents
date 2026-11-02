"""pytest.yml wiring for flaky test detection: detect only, never masking."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
GATE = "failure() && steps.run-pytest.outcome == 'failure'"

RERUN_NAME = "Rerun failed tests once (flaky detection)"
REPORT_NAME = "Report flaky tests (detect only)"
UPLOAD_NAME = "Upload flaky test report"


def _steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["test"]["steps"]


def _step(name: str) -> dict:
    """The step with this name, so inserting a step cannot silently retarget a test."""
    return next(step for step in _steps() if step.get("name") == name)


def _run_pytest() -> dict:
    return next(step for step in _steps() if step.get("id") == "run-pytest")


def test_run_pytest_keeps_failing_the_job():
    assert "continue-on-error" not in _run_pytest()


def test_flaky_steps_run_only_after_a_failed_run_and_never_mask():
    for step in (_step(RERUN_NAME), _step(REPORT_NAME), _step(UPLOAD_NAME)):
        assert step["if"] == GATE
        assert "continue-on-error" not in step


def test_rerun_runs_immediately_after_run_pytest():
    """The rerun reads the cache that the steps below Run pytest overwrite."""
    steps = _steps()
    run_pytest = steps.index(_run_pytest())
    assert steps[run_pytest + 1].get("name") == RERUN_NAME


def test_rerun_is_bounded_and_leaves_the_leg_junit_alone():
    rerun = _step(RERUN_NAME)
    assert "flaky_test_report.py rerun" in rerun["run"]
    assert rerun["timeout-minutes"] <= 3
    assert "matrix.junit_file" not in rerun["run"]


def test_report_reads_the_first_run_junit_and_uploads_json():
    report = _step(REPORT_NAME)
    assert "flaky_test_report.py report" in report["run"]
    assert "--first-junit ${{ matrix.junit_file }}" in report["run"]
    upload = _step(UPLOAD_NAME)
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["path"].endswith("flaky-tests.json")


def test_rerun_output_never_reaches_the_result_artifacts():
    """The wall-time and slow-test gates read the first run only.

    The rerun writes its JUnit file under artifacts/flaky/. If the results
    upload picked that up, the same tests would be counted twice and a rerun
    leg could trip a duration gate on a measurement that is not the leg.
    """
    path = _step("Upload test results")["with"]["path"]
    patterns = path.split() if isinstance(path, str) else list(path)
    assert "!artifacts/flaky/" in patterns

    for name, step in ((s.get("name"), s) for s in _steps()):
        run = step.get("run")
        if not isinstance(run, str) or "pytest-results-" not in run:
            continue
        assert "artifacts/flaky/" not in run, f"gate step {name!r} reads the rerun output"
