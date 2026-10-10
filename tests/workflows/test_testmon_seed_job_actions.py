"""Every action in the `testmon-seed` job is pinned and already used by the file."""

from __future__ import annotations

import re
from typing import Any

from tests.workflows.pytest_workflow_helpers import JOB_NAME, seed_job, seed_step, workflow

_SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _remote_actions(steps: list[dict[str, Any]]) -> set[str]:
    return {step["uses"] for step in steps if "uses" in step and not step["uses"].startswith("./")}


def test_every_action_is_pinned_to_a_commit_sha() -> None:
    actions = _remote_actions(seed_job()["steps"])
    assert actions
    assert all(_SHA_PIN.match(action) for action in actions), actions


def test_the_job_adds_no_action_the_file_does_not_already_use() -> None:
    others: set[str] = set()
    for name, job in workflow()["jobs"].items():
        if name != JOB_NAME:
            others |= _remote_actions(job["steps"])
    assert _remote_actions(seed_job()["steps"]) <= others


def test_checkout_does_not_persist_credentials() -> None:
    checkout = next(
        s for s in seed_job()["steps"] if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["persist-credentials"] is False


def test_the_upload_includes_the_hidden_database_and_survives_failed_partitions() -> None:
    """upload-artifact skips dotfiles unless told otherwise; the file is `.testmondata`."""
    step = seed_step("Upload the testmon database")
    assert step["with"]["path"] == ".testmondata"
    assert step["with"]["include-hidden-files"] is True
    assert step["with"]["if-no-files-found"] == "error"
    assert "!cancelled()" in step["if"]
    assert "hashFiles('.testmondata')" in step["if"]
