"""Supply-chain and trust regression tests for the PR-gated CLI smoke workflow.

CWE-829 applies because npm package lifecycle scripts execute third-party code.
The install step must use reviewed versions without access to credentials. The
workflow has three CLI legs (Codex, Claude hook discovery, Pi). None runs in an
environment or reads a secret, because the Claude and Copilot prompt legs were
deleted with their agent-* environments. This file covers the environment and
install pins; credential scope and gate wiring live in the
``test_cli_smoke_security_*`` siblings. Shared helpers live in
``tests/lib/cli_smoke_workflow.py`` and ``tests/lib/cli_smoke_fixtures.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    INSTALL_JOBS,
    PACKAGE_DIR,
    SECRET_NAMES,
    WORKFLOW,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


def test_no_job_declares_an_environment(workflow_doc: dict[Any, Any]) -> None:
    """Negative: no leg sits behind an approval environment or can claim a provider secret."""
    for name, job in workflow_doc["jobs"].items():
        assert "environment" not in job, name


def test_environment_is_not_the_retired_shared_gate() -> None:
    """Negative: the retired shared environment never returns."""
    assert "agent-approval" not in WORKFLOW.read_text(encoding="utf-8")


def test_no_job_reads_the_secrets_context(workflow_doc: dict[Any, Any]) -> None:
    """Negative: setup and npm lifecycle scripts cannot read secrets in any job."""
    assert "secrets." not in str(workflow_doc)


def test_job_scope_contains_no_smoke_credentials(workflow_doc: dict[Any, Any]) -> None:
    """Negative: no job-level env carries a smoke secret."""
    for name, job in workflow_doc["jobs"].items():
        assert SECRET_NAMES.isdisjoint(job.get("env") or {}), name


@pytest.mark.parametrize("job_name", sorted(INSTALL_JOBS))
def test_cli_install_uses_npm_ci_on_its_own_lockfile_only(
    workflow_doc: dict[Any, Any], job_name: str
) -> None:
    """Positive: each leg installs from the committed lockfile, for its own CLI only."""
    package, step_name = INSTALL_JOBS[job_name]
    install = _step_by_name(workflow_doc["jobs"][job_name], step_name)

    assert install["working-directory"] == f".github/cli-smoke/{PACKAGE_DIR[package]}"
    assert "npm ci" in install["run"]
    others = [name for name in PACKAGE_DIR if name != package]
    assert not [name for name in others if name in str(install)]
