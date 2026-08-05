"""Contract test: the test job in pytest.yml must have a finite timeout.

Issue #4502: the test job had no timeout-minutes, so a hung pytest session
would hold a runner for GitHub's 360-minute default before terminating.
The measured p99 wall time is 1546 seconds (26 min) under fleet load.
The 45-minute budget allows 1.7x that worst case and terminates genuine
hangs well before the 6-hour default.
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

        p99 suite wall time is 1546 s (~26 min). A ceiling of 60 min allows
        2.3x that and still terminates genuine hangs in under an hour. 60 is
        the upper bound this test enforces, not the configured value: the
        workflow sets 45, which allows 1.7x.
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
