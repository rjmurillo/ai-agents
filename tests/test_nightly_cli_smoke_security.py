"""Supply-chain regression tests for the nightly real-CLI smoke workflow.

CWE-829 applies because npm package lifecycle scripts execute third-party code.
The install step must use reviewed versions without access to smoke credentials.

The smoke job is a ``cli`` x ``os`` matrix. Each leg runs in the ``agent-<cli>``
environment, installs only its own CLI, and receives only its own credential.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nightly-cli-smoke.yml"
RENOVATE_CONFIG = REPO_ROOT / "renovate.json"
CLIS = ("claude", "copilot")
CLI_SECRET = {"claude": "ANTHROPIC_API_KEY", "copilot": "COPILOT_GITHUB_TOKEN"}
SECRET_NAMES = set(CLI_SECRET.values())
CLI_PACKAGE = {"claude": "@anthropic-ai/claude-code", "copilot": "@github/copilot"}
PACKAGE_VERSION_ENV = {
    "@anthropic-ai/claude-code": "CLAUDE_CODE_VERSION",
    "@github/copilot": "COPILOT_CLI_VERSION",
}
INSTALL_STEP = {"claude": "Install pinned Claude CLI", "copilot": "Install pinned Copilot CLI"}
HOOK_STEP = {
    "claude": "Run real-CLI hook smoke (claude)",
    "copilot": "Run real-CLI hook smoke (copilot)",
}
PLUGIN_STEP = {
    "claude": "Run real-CLI plugin-load smoke (claude)",
    "copilot": "Run real-CLI plugin-load smoke (copilot)",
}
CREDENTIAL_STEPS = set(HOOK_STEP.values()) | set(PLUGIN_STEP.values())
SMOKE_FILES = {
    "hook": "tests/e2e/test_cli_hook_e2e.py",
    "plugin": "tests/e2e/test_plugin_load_smoke.py",
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


def _collected_count(test_file: str, cli: str) -> int:
    """Count the tests ``-m "smoke and <cli>"`` selects, with RUN_CLI_E2E unset."""
    env = {k: v for k, v in os.environ.items() if k != "RUN_CLI_E2E"}
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", test_file, "-m", f"smoke and {cli}",
            "--collect-only", "-q", "-o", "addopts=",
        ],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


def _expected_count(step: dict[str, Any]) -> int:
    arguments = shlex.split(step["run"])
    assert arguments.count("--expected-count") == 1
    return int(arguments[arguments.index("--expected-count") + 1])


def test_matrix_runs_one_leg_per_cli_on_each_os(smoke_job: dict[str, Any]) -> None:
    """Positive: the matrix splits by CLI and keeps all three operating systems."""
    matrix = smoke_job["strategy"]["matrix"]
    assert matrix["cli"] == list(CLIS)
    assert matrix["os"] == ["ubuntu-latest", "macos-latest", "windows-latest"]
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
def test_cli_install_uses_exact_version_for_its_own_cli_only(
    smoke_job: dict[str, Any], cli: str
) -> None:
    """Positive: each install step resolves one reviewed package version, on its leg."""
    install = _step_by_name(smoke_job, INSTALL_STEP[cli])
    package = CLI_PACKAGE[cli]
    env_name = PACKAGE_VERSION_ENV[package]

    assert install["if"] == f"matrix.cli == '{cli}'"
    assert SEMVER.fullmatch(smoke_job["env"][env_name])
    assert f"{package}@${{{env_name}}}" in install["run"]
    other = next(p for p in CLI_PACKAGE.values() if p != package)
    assert other not in install["run"]


def test_cli_pins_receive_renovate_updates(
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
    assert package_rule["automerge"] is True
    assert package_rule["minimumReleaseAge"] == "7 days"
    assert set(package_rule["matchUpdateTypes"]) == {"major", "minor", "patch"}


@pytest.mark.parametrize("cli", CLIS)
def test_install_step_has_no_secret_environment(smoke_job: dict[str, Any], cli: str) -> None:
    """Edge: a later workflow edit cannot reintroduce install-step secrets."""
    install = _step_by_name(smoke_job, INSTALL_STEP[cli])
    install_env = install.get("env") or {}

    assert SECRET_NAMES.isdisjoint(install_env)
    assert "secrets." not in install["run"]


@pytest.mark.parametrize("cli", CLIS)
@pytest.mark.parametrize("steps", [HOOK_STEP, PLUGIN_STEP], ids=["hook", "plugin"])
def test_cli_step_receives_only_its_own_credential(
    smoke_job: dict[str, Any], steps: dict[str, str], cli: str
) -> None:
    """Positive: a leg's CLI step gets exactly its provider secret and no other."""
    step = _step_by_name(smoke_job, steps[cli])

    assert set(step["env"]) == {CLI_SECRET[cli]}
    assert step["env"][CLI_SECRET[cli]] == f"${{{{ secrets.{CLI_SECRET[cli]} }}}}"
    assert f"matrix.cli == '{cli}'" in step["if"]


@pytest.mark.parametrize("cli", CLIS)
@pytest.mark.parametrize("steps", [HOOK_STEP, PLUGIN_STEP], ids=["hook", "plugin"])
def test_cli_step_selects_only_its_own_marker(
    smoke_job: dict[str, Any], steps: dict[str, str], cli: str
) -> None:
    """Negative: a leg cannot run the other provider's tests, which would skip."""
    arguments = shlex.split(_step_by_name(smoke_job, steps[cli])["run"])
    other = next(c for c in CLIS if c != cli)

    marker_expression = arguments[arguments.index("-m") + 1]
    assert marker_expression == f"smoke and {cli}"
    assert other not in marker_expression


def test_non_cli_steps_receive_no_credentials(smoke_job: dict[str, Any]) -> None:
    """Negative: credentials do not leak to checkout, setup, install, or checks."""
    for step in smoke_job["steps"]:
        if step.get("name") in CREDENTIAL_STEPS:
            continue
        step_env = step.get("env") or {}
        assert SECRET_NAMES.isdisjoint(step_env)


def test_credential_steps_exist_for_every_cli_and_smoke(smoke_job: dict[str, Any]) -> None:
    """Guard: the exemption list above cannot drift from the real step names."""
    names = {step.get("name") for step in smoke_job["steps"]}
    assert CREDENTIAL_STEPS <= names
    with_secrets = {s["name"] for s in smoke_job["steps"] if "secrets." in str(s.get("env"))}
    assert with_secrets == CREDENTIAL_STEPS


@pytest.mark.parametrize("cli", CLIS)
def test_expected_counts_match_the_collected_smoke_tests(
    smoke_job: dict[str, Any], cli: str
) -> None:
    """Edge: both gates demand every test the leg's marker selects, no fewer."""
    hook_gate = _step_by_name(smoke_job, "Assert the hook smoke actually ran")
    plugin_gate = _step_by_name(smoke_job, "Assert the plugin-load smoke actually ran")

    assert _expected_count(hook_gate) == _collected_count(SMOKE_FILES["hook"], cli)
    assert _expected_count(plugin_gate) == _collected_count(SMOKE_FILES["plugin"], cli)


def test_plugin_load_gate_matches_its_file(smoke_job: dict[str, Any]) -> None:
    """Edge: the plugin-load gate filters on the plugin-load smoke module."""
    gate = _step_by_name(smoke_job, "Assert the plugin-load smoke actually ran")
    arguments = shlex.split(gate["run"])

    assert arguments.count("--smoke-substr") == 1
    assert arguments[arguments.index("--smoke-substr") + 1] == "test_plugin_load_smoke"


def test_install_isolation_smoke_runs_only_on_the_copilot_leg(
    smoke_job: dict[str, Any],
) -> None:
    """Positive and negative: the credential-free copilot smoke skips the claude leg."""
    run = _step_by_name(smoke_job, "Run Copilot install isolation smoke")
    gate = _step_by_name(smoke_job, "Assert the install isolation smoke actually ran")

    assert run["if"] == "always() && matrix.cli == 'copilot'"
    assert gate["if"] == "always() && matrix.cli == 'copilot'"
    assert "TestCopilotBinaryInstall" in run["run"]
    assert _expected_count(gate) == 1
    assert not (run.get("env") or {})


def test_gates_still_run_after_a_failed_smoke(smoke_job: dict[str, Any]) -> None:
    """Edge: every assert step keeps always(), so a skip still turns the leg red."""
    for step in smoke_job["steps"]:
        if str(step.get("name", "")).startswith("Assert the "):
            assert "always()" in step["if"], step["name"]
