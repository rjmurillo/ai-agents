"""pytest.yml wiring for flaky test detection: detect only, never masking."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
GATE = "failure() && steps.run-pytest.outcome == 'failure'"


def _flaky_steps() -> list[dict]:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["test"]["steps"]
    index = next(i for i, step in enumerate(steps) if step.get("id") == "run-pytest")
    return steps[index : index + 4]


def test_run_pytest_keeps_failing_the_job():
    main_step = _flaky_steps()[0]
    assert "continue-on-error" not in main_step


def test_flaky_steps_run_only_after_a_failed_run_and_never_mask():
    for step in _flaky_steps()[1:]:
        assert step["if"] == GATE
        assert "continue-on-error" not in step


def test_rerun_is_bounded_and_leaves_the_leg_junit_alone():
    rerun = _flaky_steps()[1]
    assert "flaky_test_report.py rerun" in rerun["run"]
    assert rerun["timeout-minutes"] <= 3
    assert "matrix.junit_file" not in rerun["run"]


def test_report_reads_the_first_run_junit_and_uploads_json():
    report, upload = _flaky_steps()[2:]
    assert "flaky_test_report.py report" in report["run"]
    assert "--first-junit ${{ matrix.junit_file }}" in report["run"]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["path"].endswith("flaky-tests.json")
