"""Supply-chain and trust regression tests for the PR-gated CLI smoke workflow.

CWE-829 applies because npm package lifecycle scripts execute third-party code.
The install step must use reviewed versions without access to smoke credentials.

The smoke job is a ``cli`` x ``os`` matrix. Each leg runs in the ``agent-<cli>``
environment, installs only its own CLI, and receives only its own credential.
This file covers the matrix and install pins; credential scope and gate wiring
live in the ``test_cli_smoke_security_*`` siblings. Shared helpers live in
``tests/lib/cli_smoke_workflow.py`` and ``tests/lib/cli_smoke_fixtures.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from tests.lib.cli_smoke_workflow import (
    CLI_PACKAGE,
    CLIS,
    INSTALL_STEP,
    OPERATING_SYSTEMS,
    PACKAGE_DIR,
    SECRET_NAMES,
    WORKFLOW,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


def test_matrix_runs_one_leg_per_cli_on_each_os(smoke_job: dict[str, Any]) -> None:
    """Positive: the matrix splits by CLI and keeps all three operating systems."""
    matrix = smoke_job["strategy"]["matrix"]
    assert matrix["cli"] == list(CLIS)
    assert matrix["os"] == OPERATING_SYSTEMS
    assert smoke_job["strategy"]["fail-fast"] is False
    assert "${{ matrix.cli }}" in smoke_job["name"]


def test_each_leg_runs_in_its_provider_environment(smoke_job: dict[str, Any]) -> None:
    """Positive: the environment follows the matrix CLI, never agent-approval."""
    assert smoke_job["environment"] == "agent-${{ matrix.cli }}"


def test_environment_is_not_the_retired_shared_gate(smoke_job: dict[str, Any]) -> None:
    """Negative: a hard-coded or shared environment would give a leg the wrong secret."""
    assert smoke_job["environment"] != "agent-approval"
    assert "agent-approval" not in WORKFLOW.read_text(encoding="utf-8")


def test_job_scope_contains_no_smoke_credentials(smoke_job: dict[str, Any]) -> None:
    """Negative: setup and npm lifecycle scripts cannot read smoke secrets."""
    assert SECRET_NAMES.isdisjoint(smoke_job["env"])


@pytest.mark.parametrize("cli", CLIS)
def test_cli_install_uses_npm_ci_on_its_own_lockfile_only(
    smoke_job: dict[str, Any], cli: str
) -> None:
    """Positive: each leg installs from the committed lockfile, for its own CLI only."""
    install = _step_by_name(smoke_job, INSTALL_STEP[cli])
    package = CLI_PACKAGE[cli]

    assert install["if"] == f"matrix.cli == '{cli}'"
    assert install["working-directory"] == f".github/cli-smoke/{PACKAGE_DIR[package]}"
    assert "npm ci" in install["run"]
    other = next(p for p in CLI_PACKAGE.values() if p != package)
    assert other not in yaml.safe_dump(install)
