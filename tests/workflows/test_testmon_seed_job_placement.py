"""The `testmon-seed` job runs only for a push to main and never gates the chain.

Issue #6239, ADR-104. The hook trusts the artifact because it came from a push
to main, and a slow or failed seed must not change `Run Python Tests`.
"""

from __future__ import annotations

import re

from tests.workflows.pytest_workflow_helpers import JOB_NAME, seed_job, workflow


def test_the_job_runs_only_for_a_push_to_main() -> None:
    condition = re.sub(r"\s+", " ", str(seed_job()["if"]))
    assert condition == "github.event_name == 'push' && github.ref == 'refs/heads/main'"


def test_no_job_waits_on_the_seed_and_it_waits_on_none() -> None:
    for name, other in workflow()["jobs"].items():
        needs = other.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        assert JOB_NAME not in needs, f"{name} waits on the seed job"
    assert JOB_NAME not in workflow()["jobs"]["test-result"]["needs"]
    assert "needs" not in seed_job()


def test_the_job_is_bounded_and_read_only() -> None:
    assert 30 < seed_job()["timeout-minutes"] <= 90
    assert seed_job()["permissions"] == {"contents": "read"}


def test_nothing_in_the_job_reads_a_pull_request_context() -> None:
    text = str(seed_job())
    assert "pull_request" not in text
    assert "github.head_ref" not in text
