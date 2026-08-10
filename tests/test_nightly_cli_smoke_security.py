"""Supply-chain regression tests for the nightly real-CLI smoke workflow.

CWE-829 applies because npm package lifecycle scripts execute third-party code.
The install step must use reviewed versions without access to smoke credentials.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "nightly-cli-smoke.yml"
RENOVATE_CONFIG = Path(__file__).resolve().parents[1] / "renovate.json"
SECRET_NAMES = {"ANTHROPIC_API_KEY", "COPILOT_GITHUB_TOKEN"}
PACKAGE_VERSION_ENV = {
    "@anthropic-ai/claude-code": "CLAUDE_CODE_VERSION",
    "@github/copilot": "COPILOT_CLI_VERSION",
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


@pytest.fixture(scope="module")
def smoke_job() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["smoke"]


@pytest.fixture(scope="module")
def renovate_config() -> dict[str, Any]:
    return yaml.safe_load(RENOVATE_CONFIG.read_text(encoding="utf-8"))


def _step_by_name(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_job_scope_contains_no_smoke_credentials(smoke_job: dict[str, Any]) -> None:
    """Negative: setup and npm lifecycle scripts cannot read smoke secrets."""
    assert SECRET_NAMES.isdisjoint(smoke_job["env"])


def test_cli_install_uses_exact_versions(smoke_job: dict[str, Any]) -> None:
    """Positive: the install command resolves reviewed package versions only."""
    install = _step_by_name(smoke_job, "Install pinned Claude and Copilot CLIs")
    command = install["run"]

    for package, env_name in PACKAGE_VERSION_ENV.items():
        version = smoke_job["env"][env_name]
        assert SEMVER.fullmatch(version)
        assert f"{package}@${{{env_name}}}" in command


def test_cli_pins_receive_reviewed_renovate_updates(
    smoke_job: dict[str, Any], renovate_config: dict[str, Any]
) -> None:
    """Edge: vendor updates stay visible without restoring floating installs."""
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    for package, env_name in PACKAGE_VERSION_ENV.items():
        marker = f"# renovate: datasource=npm depName={package}"
        assert f"{marker}\n      {env_name}:" in workflow_text

    managers = renovate_config["customManagers"]
    assert any(
        "nightly-cli-smoke" in " ".join(manager["managerFilePatterns"]) for manager in managers
    )
    package_rule = next(
        rule
        for rule in renovate_config["packageRules"]
        if set(rule.get("matchPackageNames") or {}) == set(PACKAGE_VERSION_ENV)
    )
    assert package_rule["automerge"] is False
    assert set(package_rule["matchUpdateTypes"]) == {"major", "minor", "patch"}

    for rule in renovate_config["packageRules"]:
        if rule.get("automerge") is not True:
            continue
        excluded = {
            name.removeprefix("!")
            for name in rule.get("matchPackageNames", [])
            if name.startswith("!")
        }
        assert set(PACKAGE_VERSION_ENV) <= excluded


def test_install_step_has_no_secret_environment(smoke_job: dict[str, Any]) -> None:
    """Edge: a later workflow edit cannot reintroduce install-step secrets."""
    install = _step_by_name(smoke_job, "Install pinned Claude and Copilot CLIs")
    install_env = install.get("env") or {}

    assert SECRET_NAMES.isdisjoint(install_env)
    assert "secrets." not in install["run"]


@pytest.mark.parametrize(
    "step_name",
    ["Run real-CLI hook smoke", "Run real-CLI plugin-load smoke"],
)
def test_only_cli_execution_steps_receive_credentials(
    smoke_job: dict[str, Any], step_name: str
) -> None:
    """Positive: authenticated CLI processes receive both required secrets."""
    step = _step_by_name(smoke_job, step_name)

    assert set(step["env"]) == SECRET_NAMES
    assert all("secrets." in value for value in step["env"].values())


def test_non_cli_steps_receive_no_credentials(smoke_job: dict[str, Any]) -> None:
    """Negative: credentials do not leak to checkout, setup, install, or checks."""
    allowed_steps = {
        "Run real-CLI hook smoke",
        "Run real-CLI plugin-load smoke",
    }

    for step in smoke_job["steps"]:
        if step.get("name") in allowed_steps:
            continue
        step_env = step.get("env") or {}
        assert SECRET_NAMES.isdisjoint(step_env)


def test_plugin_load_gate_rejects_any_skipped_smoke(
    smoke_job: dict[str, Any],
) -> None:
    """Edge: all five plugin and agent-contract cases must run."""
    gate = _step_by_name(smoke_job, "Assert the plugin-load smoke actually ran")
    arguments = shlex.split(gate["run"])

    assert arguments.count("--smoke-substr") == 1
    assert arguments[arguments.index("--smoke-substr") + 1] == "test_plugin_load_smoke"
    assert arguments.count("--expected-count") == 1
    assert arguments[arguments.index("--expected-count") + 1] == "5"
