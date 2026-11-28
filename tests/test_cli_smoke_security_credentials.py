"""Credential-scope tests for the PR-gated CLI smoke workflow (REQ-047 AC3, AC9).

No step receives a provider credential. The Claude and Copilot prompt legs that
did were deleted, so each CLI leg runs with no secret in its environment.
"""

from __future__ import annotations

import shlex
from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    EVERY_MODEL_SECRET,
    INSTALL_JOBS,
    SECRET_NAMES,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


@pytest.mark.parametrize("job_name", sorted(INSTALL_JOBS))
def test_install_step_has_no_secret_environment(
    workflow_doc: dict[Any, Any], job_name: str
) -> None:
    """Edge: a later workflow edit cannot reintroduce install-step secrets."""
    _, step_name = INSTALL_JOBS[job_name]
    install = _step_by_name(workflow_doc["jobs"][job_name], step_name)

    assert set(install.get("env") or {}) <= {"BIN_DIR"}
    assert "secrets." not in install["run"]


def test_no_step_receives_a_credential(workflow_doc: dict[Any, Any]) -> None:
    """Negative: credentials reach no checkout, setup, install, CLI, or gate step."""
    for job_name, job in workflow_doc["jobs"].items():
        for step in job["steps"]:
            step_env = step.get("env") or {}
            assert EVERY_MODEL_SECRET.isdisjoint(step_env), (job_name, step.get("name"))
            assert "secrets." not in str(step_env), (job_name, step.get("name"))


def test_hook_discovery_step_selects_only_the_claude_marker(hooks_job: dict[str, Any]) -> None:
    """Negative: the hook discovery leg cannot select a provider prompt test."""
    step = _step_by_name(hooks_job, "Run real-CLI hook discovery smoke (claude)")
    arguments = shlex.split(step["run"])

    assert arguments[arguments.index("-m") + 1] == "smoke and claude"
    assert "tests/e2e/test_claude_hook_discovery_smoke.py" in arguments
    assert SECRET_NAMES.isdisjoint(step.get("env") or {})
