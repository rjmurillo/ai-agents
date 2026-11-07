"""Lockfile install tests for the CLI smoke workflow (#6506 workflow-ci-01).

Each CLI installs with ``npm ci`` from its own ``.github/cli-smoke/<cli>/`` manifest and
lockfile, so npm checks integrity and Renovate maintains the pin natively. The matrix,
credential, and gate tests stay in ``tests/test_cli_smoke_security.py``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from tests.lib.cli_smoke_workflow import (
    CLI_SMOKE_DIR,
    PACKAGE_DIR,
    SEMVER,
    WORKFLOW,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


def load_package_json(package: str) -> dict[str, Any]:
    path = CLI_SMOKE_DIR / PACKAGE_DIR[package] / "package.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_package_lock(package: str) -> dict[str, Any]:
    path = CLI_SMOKE_DIR / PACKAGE_DIR[package] / "package-lock.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _install_steps() -> dict[str, dict[str, Any]]:
    """Map each CLI package to its parsed install step across every smoke job."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    found: dict[str, dict[str, Any]] = {}
    for job in jobs.values():
        for step in job.get("steps", []):
            directory = step.get("working-directory", "")
            for package, name in PACKAGE_DIR.items():
                if directory == f".github/cli-smoke/{name}":
                    found[package] = step
    return found


def test_no_run_field_resolves_a_version_at_run_time() -> None:
    """Negative: `npm install -g <pkg>@<version>` has no integrity check (workflow-ci-01)."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    runs = [step.get("run", "") for job in jobs.values() for step in job.get("steps", [])]
    assert not [run for run in runs if "npm install" in run]
    assert not [run for run in runs if any(f"{package}@" in run for package in PACKAGE_DIR)]


@pytest.mark.parametrize("package", sorted(PACKAGE_DIR))
def test_install_step_keeps_the_cli_on_path(package: str) -> None:
    """Positive: later steps find the CLI because its own install step extends GITHUB_PATH."""
    step = _install_steps()[package]
    bin_dir = f"/.github/cli-smoke/{PACKAGE_DIR[package]}/node_modules/.bin"
    assert step["env"]["BIN_DIR"] == "${{ github.workspace }}" + bin_dir
    assert 'echo "$BIN_DIR" >> "$GITHUB_PATH"' in step["run"]


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
        if path == "" or entry.get("link"):
            continue
        assert entry["resolved"].startswith("https://registry.npmjs.org/"), path
        assert entry["integrity"].startswith("sha512-"), path


def test_pi_install_skips_lifecycle_scripts() -> None:
    """Edge: the Pi leg keeps the --ignore-scripts hardening it had with `npm install -g`."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = _step_by_name(workflow["jobs"]["smoke-pi"], "Install pinned Pi CLI")
    assert "npm ci --ignore-scripts" in step["run"]


def test_cli_pins_receive_native_renovate_updates(renovate_config: dict[str, Any]) -> None:
    """Edge: Renovate's npm manager bumps manifest and lockfile; the regex pins are gone."""
    assert "# renovate: datasource" not in WORKFLOW.read_text(encoding="utf-8")
    package_rule = next(
        rule
        for rule in renovate_config["packageRules"]
        if set(rule.get("matchPackageNames") or {}) == set(PACKAGE_DIR)
    )
    # The later file-glob exemption overrides this automerge for the cli-smoke files.
    assert package_rule["automerge"] is True
    assert package_rule["minimumReleaseAge"] == "7 days"
    assert set(package_rule["matchUpdateTypes"]) == {"major", "minor", "patch"}
