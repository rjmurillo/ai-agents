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
    SEMVER,
    WORKFLOW,
    _step_by_name,
    load_package_json,
    load_package_lock,
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


@pytest.mark.parametrize("package", sorted(PACKAGE_DIR))
def test_no_install_step_resolves_a_version_at_run_time(package: str) -> None:
    """Negative: `npm install -g <pkg>@<version>` has no integrity check (workflow-ci-01)."""
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    assert "npm install" not in workflow_text
    assert f"{package}@" not in workflow_text
    assert "_CLI_VERSION" not in workflow_text
    assert "CLAUDE_CODE_VERSION" not in workflow_text


@pytest.mark.parametrize("package", sorted(PACKAGE_DIR))
def test_install_steps_keep_the_cli_on_path(package: str) -> None:
    """Positive: later steps find the CLI because the install step extends GITHUB_PATH."""
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    bin_dir = f".github/cli-smoke/{PACKAGE_DIR[package]}/node_modules/.bin"
    assert bin_dir in workflow_text
    assert '>> "$GITHUB_PATH"' in workflow_text


@pytest.mark.parametrize("package", sorted(PACKAGE_DIR))
def test_package_json_pins_one_exact_version(package: str) -> None:
    """Positive: the manifest names the CLI once, with an exact version (no range)."""
    manifest = load_package_json(package)

    assert manifest["private"] is True
    assert list(manifest["dependencies"]) == [package]
    assert SEMVER.fullmatch(manifest["dependencies"][package])


@pytest.mark.parametrize("package", sorted(PACKAGE_DIR))
def test_lockfile_matches_manifest_and_carries_integrity(package: str) -> None:
    """Edge: `npm ci` fails on drift, and every locked tarball has a hash to verify."""
    manifest = load_package_json(package)
    lock = load_package_lock(package)

    assert lock["lockfileVersion"] >= 3
    root_deps = lock["packages"][""]["dependencies"]
    assert root_deps == manifest["dependencies"]
    locked = lock["packages"][f"node_modules/{package}"]
    assert locked["version"] == manifest["dependencies"][package]
    for path, entry in lock["packages"].items():
        if path == "":
            continue
        assert entry["resolved"].startswith("https://registry.npmjs.org/"), path
        assert entry["integrity"].startswith("sha512-"), path


def test_pi_install_skips_lifecycle_scripts() -> None:
    """Edge: the Pi leg keeps the --ignore-scripts hardening it had with `npm install -g`."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = _step_by_name(workflow["jobs"]["smoke-pi"], "Install pinned Pi CLI")
    assert "npm ci --ignore-scripts" in step["run"]


def test_cli_pins_receive_native_renovate_updates(renovate_config: dict[str, Any]) -> None:
    """Edge: Renovate's npm manager bumps manifest and lockfile; no regex manager remains."""
    assert "customManagers" not in renovate_config
    assert "renovate:" not in WORKFLOW.read_text(encoding="utf-8")
    package_rule = next(
        rule
        for rule in renovate_config["packageRules"]
        if set(rule.get("matchPackageNames") or {}) == set(PACKAGE_DIR)
    )
    assert package_rule["automerge"] is True
    assert package_rule["minimumReleaseAge"] == "7 days"
    assert set(package_rule["matchUpdateTypes"]) == {"major", "minor", "patch"}
