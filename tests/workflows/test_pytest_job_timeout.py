"""Contract test: the test job in pytest.yml must have a finite timeout.

Issue #4502: the test job had no timeout-minutes, so a hung pytest session
would hold a runner for GitHub's 360-minute default before terminating.
Its evidence records run 30830624080 at 986 seconds and one parallel-fleet
run at 1546 seconds (26 min), the worst observation, not a percentile.

Thirty minutes leaves only 1.2x the worst observation, too little for runner
contention. Sixty minutes leaves 2.3x but doubles the time to stop a genuine
hang versus 30. The configured 45 minutes is the midpoint: 1.7x measured
headroom while cutting the unbounded default from 6 hours to 45 minutes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"


def _load_workflow() -> dict[str, Any]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        return cast(dict[str, Any], yaml.safe_load(handle))


class TestTestJobTimeout:
    def test_test_job_has_timeout_minutes(self) -> None:
        """The test job must set timeout-minutes to a finite value.

        Without this, a deadlocked fixture or an infinite-loop regression
        holds a runner for the full 360-minute GitHub default.
        """
        workflow = _load_workflow()
        jobs = workflow.get("jobs", {})
        assert "test" in jobs, "pytest.yml must have a 'test' job"
        test_job = jobs["test"]
        assert "timeout-minutes" in test_job, (
            "The 'test' job in pytest.yml has no timeout-minutes. "
            "A hung suite will burn 360 minutes before GitHub terminates it. "
            "See issue #4502."
        )

    def test_test_job_timeout_is_at_most_60_minutes(self) -> None:
        """The timeout must not be so large that it defeats the purpose.

        Issue #4502 records the worst observed suite wall time as 1546 s
        (~26 min), from a parallel-fleet run, not a p99. A ceiling of 60 min
        allows 2.3x that and still terminates genuine hangs in under an hour.
        Sixty is the upper bound this test enforces, not the configured value:
        the workflow sets 45 (1.7x); 30 (1.2x) was rejected as too close to
        the observed run under contention.
        """
        workflow = _load_workflow()
        jobs = workflow.get("jobs", {})
        test_job = jobs.get("test", {})
        timeout = test_job.get("timeout-minutes")
        assert timeout is not None, "timeout-minutes not set"
        assert isinstance(timeout, int), f"timeout-minutes must be an integer, got {timeout!r}"
        assert timeout <= 60, (
            f"timeout-minutes is {timeout}, above the 60 min ceiling. Measured p99 "
            f"suite wall time is 26 min, so 60 already allows 2.3x it. {timeout} "
            f"allows {timeout / 26:.1f}x and delays termination of a genuine hang "
            "by that much."
        )
