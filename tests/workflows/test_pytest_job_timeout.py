"""Contract test: jobs in pytest.yml must have bounded timeouts.

Issue #4854 caps every job in this workflow at 10 minutes. The matrix
partitions each run a bounded subset of the suite, while orchestration jobs
retain shorter limits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"

_MAX_TIMEOUT = 10


def _load_workflow() -> dict[str, Any]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        return cast(dict[str, Any], yaml.safe_load(handle))


class TestTestJobTimeout:
    def test_test_job_has_timeout_minutes(self) -> None:
        """The test job must set timeout-minutes to a finite value."""
        workflow = _load_workflow()
        jobs = workflow.get("jobs", {})
        assert "test" in jobs, "pytest.yml must have a 'test' job"
        test_job = jobs["test"]
        assert "timeout-minutes" in test_job, (
            "The 'test' job in pytest.yml has no timeout-minutes. "
            "A hung suite will burn 360 minutes before GitHub terminates it."
        )

    def test_test_job_timeout_is_10_minutes(self) -> None:
        """Issue #4854: partitioned matrix legs complete in under 10 minutes."""
        workflow = _load_workflow()
        timeout = workflow["jobs"]["test"]["timeout-minutes"]
        assert timeout == _MAX_TIMEOUT, (
            f"timeout-minutes is {timeout}, expected {_MAX_TIMEOUT} (issue #4854)."
        )

    def test_coverage_job_timeout_is_10_minutes(self) -> None:
        """The coverage combine job must also be bounded."""
        workflow = _load_workflow()
        timeout = workflow["jobs"]["coverage"]["timeout-minutes"]
        assert timeout == _MAX_TIMEOUT

    def test_security_job_timeout_is_10_minutes(self) -> None:
        """Security checks must be bounded."""
        workflow = _load_workflow()
        timeout = workflow["jobs"]["security"]["timeout-minutes"]
        assert timeout == _MAX_TIMEOUT

    def test_every_job_is_bounded_at_10_minutes(self) -> None:
        workflow = _load_workflow()
        for name, job in workflow["jobs"].items():
            timeout = job.get("timeout-minutes")
            assert isinstance(timeout, int), f"{name} has no integer timeout"
            assert timeout <= _MAX_TIMEOUT, f"{name} timeout is {timeout} minutes"
