"""Contract test: the test job in pytest.yml must have a finite timeout.

Issue #4502: the test job had no timeout-minutes, so a hung pytest session
would hold a runner for GitHub's 360-minute default before terminating.
Its evidence records run 30830624080 at 986 seconds and one parallel-fleet
run at 1546 seconds (26 min), the worst observation, not a percentile. This
is a two-observation operational guardrail, not a distribution estimate.
The CI run's complete job took 17.2 minutes; the fleet record covers pytest
runtime only, so the remaining 19 minutes for setup, coverage gates, and
artifact upload is a conservative assumption, not measured phase headroom.
No comparable failed or cancelled-run dataset exists. The review trigger below
collects new runtime evidence before the limit changes.

Thirty minutes leaves only 1.2x the worst observation, too little for runner
contention. Sixty minutes leaves 2.3x but doubles the time to stop a genuine
hang versus 30. The configured 45 minutes is the midpoint: 1.7x measured
headroom while cutting the unbounded default from 6 hours to 45 minutes.

A false timeout from legitimate suite growth is the known failure mode.
Re-measure before changing the limit when either one non-hung run reaches 45
minutes, or three non-cancelled `Run Python Tests` jobs exceed 36 minutes
(80% of the limit) within 30 days. One infrastructure failure is not evidence
to raise the ceiling. Keep 45 unless that trigger supplies new runtime data.
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

    def test_test_job_timeout_is_45_minutes(self) -> None:
        """The timeout must match the measured 45-minute policy.

        Issue #4502 records the worst observed suite wall time as 1546 s
        (~26 min), from a parallel-fleet run, not a p99. Thirty minutes gives
        1.2x headroom and was rejected as too close under runner contention.
        Sixty gives 2.3x but doubles hang time versus 30. Forty-five is the
        selected midpoint at 1.7x.
        """
        workflow = _load_workflow()
        jobs = workflow.get("jobs", {})
        test_job = jobs.get("test", {})
        timeout = test_job.get("timeout-minutes")
        assert timeout is not None, "timeout-minutes not set"
        assert isinstance(timeout, int), f"timeout-minutes must be an integer, got {timeout!r}"
        assert timeout == 45, (
            f"timeout-minutes is {timeout}, expected the measured 45 min policy. "
            "Issue #4502 records a 26 min worst observation: 30 gives only 1.2x "
            "headroom, while 60 delays hang termination without evidence that "
            "2.3x is needed."
        )
