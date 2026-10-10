"""The 480 s leg gate is blocking: it runs in a job the required check needs."""

from __future__ import annotations

from tests.ci.pytest_split_workflow_helpers import workflow_jobs


def _gate_step() -> dict:
    (step,) = [
        s
        for s in workflow_jobs()["coverage"]["steps"]
        if s.get("name") == "Gate pytest leg wall time"
    ]
    return step


class TestLegGateWiring:
    def test_the_gate_step_is_in_the_coverage_job(self) -> None:
        assert "duration_gate_check.py" in _gate_step()["run"]

    def test_the_required_check_needs_the_coverage_job(self) -> None:
        assert "coverage" in workflow_jobs()["test-result"]["needs"]

    def test_the_gate_reads_every_matrix_junit_file(self) -> None:
        matrix = workflow_jobs()["test"]["strategy"]["matrix"]["include"]
        for leg in matrix:
            assert leg["junit_file"] in _gate_step()["run"]

    def test_the_gate_step_is_not_advisory(self) -> None:
        assert "continue-on-error" not in _gate_step()

    def test_the_non_required_duration_job_does_not_carry_the_gate(self) -> None:
        run = " ".join(str(s.get("run", "")) for s in workflow_jobs()["test-durations"]["steps"])
        assert "duration_gate_check.py" not in run
