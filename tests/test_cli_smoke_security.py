"""Supply-chain and trust regression tests for the PR-gated CLI smoke workflow.

CWE-829 applies because npm package lifecycle scripts execute third-party code.
The install step must use reviewed versions without access to smoke credentials.

The smoke job is a ``cli`` x ``os`` matrix. Each leg runs in the ``agent-<cli>``
environment, installs only its own CLI, and receives only its own credential.
The Codex job reads no credential and runs in no environment (REQ-047 AC11).
The workflow triggers on ``pull_request``, so a fork PR must fail closed with a
message naming the fork (REQ-047 AC12).
"""

from __future__ import annotations

import re
import shlex
import sys
from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    CLI_PACKAGE,
    CLI_SECRET,
    CLIS,
    CREDENTIAL_STEPS,
    HOOK_STEP,
    INSTALL_STEP,
    OPERATING_SYSTEMS,
    PACKAGE_VERSION_ENV,
    PLUGIN_STEP,
    REPO_ROOT,
    SECRET_NAMES,
    SEMVER,
    SMOKE_FILES,
    WORKFLOW,
    _collected_count,
    _expected_count,
    _step_by_name,
    load_renovate_config,
    load_workflow,
)


@pytest.fixture(scope="module")
def workflow_doc() -> dict[Any, Any]:
    return load_workflow()


@pytest.fixture(scope="module")
def smoke_job(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    return workflow_doc["jobs"]["smoke"]


@pytest.fixture(scope="module")
def codex_job(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    return workflow_doc["jobs"]["smoke-codex"]


@pytest.fixture(scope="module")
def renovate_config() -> dict[str, Any]:
    return load_renovate_config()


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


def test_cli_pins_receive_renovate_updates(renovate_config: dict[str, Any]) -> None:
    """Edge: vendor updates stay visible without restoring floating installs."""
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    for package, env_name in PACKAGE_VERSION_ENV.items():
        marker = f"# renovate: datasource=npm depName={package}"
        assert f"{marker}\n      {env_name}: '" in workflow_text

    managers = renovate_config["customManagers"]
    patterns = [" ".join(manager["managerFilePatterns"]) for manager in managers]
    assert any("plugin-cli-smoke" in joined for joined in patterns)
    assert not any("nightly" in joined for joined in patterns)
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


HOOK_GATE = {
    "claude": "Assert the hook smoke actually ran (claude)",
    "copilot": "Assert the hook smoke actually ran (copilot)",
}
PLUGIN_GATE = {
    "claude": "Assert the plugin-load smoke actually ran (claude)",
    "copilot": "Assert the plugin-load smoke actually ran (copilot)",
}
QUOTA_SKIP_MARKER = "QUOTA_SKIP:"


@pytest.mark.parametrize("cli", CLIS)
def test_expected_counts_match_the_collected_smoke_tests(
    smoke_job: dict[str, Any], cli: str
) -> None:
    """Edge: both gates demand every test the leg's marker selects, no fewer."""
    hook_gate = _step_by_name(smoke_job, HOOK_GATE[cli])
    plugin_gate = _step_by_name(smoke_job, PLUGIN_GATE[cli])

    assert _expected_count(hook_gate) == _collected_count(SMOKE_FILES["hook"], cli)
    assert _expected_count(plugin_gate) == _collected_count(SMOKE_FILES["plugin"], cli)


@pytest.mark.parametrize("cli", CLIS)
def test_each_gate_runs_only_on_its_own_leg(smoke_job: dict[str, Any], cli: str) -> None:
    """Positive and negative: a leg runs its own gates and not the other leg's."""
    other = next(c for c in CLIS if c != cli)
    for gates in (HOOK_GATE, PLUGIN_GATE):
        step = _step_by_name(smoke_job, gates[cli])
        assert step["if"] == f"always() && matrix.cli == '{cli}'"
        assert f"matrix.cli == '{other}'" not in step["if"]


def _gate_arguments(step: dict[str, Any]) -> list[str]:
    return shlex.split(step["run"])


ZERO_TOKEN_TEST = {
    "claude": "test_claude_plugin_loads_expected_skills",
    "copilot": "test_copilot_plugin_loads_expected_skills",
}


def _option_values(arguments: list[str], option: str) -> list[str]:
    return [arguments[i + 1] for i, value in enumerate(arguments) if value == option]


@pytest.mark.parametrize("cli", CLIS)
@pytest.mark.parametrize("gates", [HOOK_GATE, PLUGIN_GATE], ids=["hook", "plugin"])
def test_claude_and_copilot_gates_allow_the_quota_skip_marker(
    smoke_job: dict[str, Any], gates: dict[str, str], cli: str
) -> None:
    """D26: budget exhaustion is an accepted gap for every provider's prompt checks."""
    arguments = _gate_arguments(_step_by_name(smoke_job, gates[cli]))

    assert _option_values(arguments, "--allow-skip-marker") == [QUOTA_SKIP_MARKER]


@pytest.mark.parametrize("cli", CLIS)
def test_plugin_load_gate_requires_the_zero_token_test_to_pass(
    smoke_job: dict[str, Any], cli: str
) -> None:
    """The zero-token load test must PASS, so a quota skip cannot make the leg green."""
    arguments = _gate_arguments(_step_by_name(smoke_job, PLUGIN_GATE[cli]))

    assert _option_values(arguments, "--require-pass") == [ZERO_TOKEN_TEST[cli]]


@pytest.mark.parametrize("cli", CLIS)
def test_required_zero_token_test_exists_and_never_skips_on_quota(cli: str) -> None:
    """Guard: the required id names a real test that does not call a skip classifier."""
    source = (REPO_ROOT / SMOKE_FILES["plugin"]).read_text(encoding="utf-8")
    name = ZERO_TOKEN_TEST[cli]
    match = re.search(rf"^def {name}\(.*?(?=^def |\Z)", source, re.DOTALL | re.MULTILINE)

    assert match is not None
    assert "_skip_on_" not in match.group(0)
    assert "_skip_or_fail_" not in match.group(0)


def test_codex_and_install_isolation_gates_stay_strict(
    smoke_job: dict[str, Any], codex_job: dict[str, Any]
) -> None:
    """Negative: neither the Codex gate nor the install-isolation gate allows a skip."""
    codex_gate = _step_by_name(codex_job, "Assert the plugin-load smoke actually ran")
    install_gate = _step_by_name(smoke_job, "Assert the install isolation smoke actually ran")

    assert "--allow-skip-marker" not in codex_gate["run"]
    assert "--allow-skip-marker" not in install_gate["run"]
    assert "--require-pass test_codex_plugin_loads_expected_skills" in " ".join(
        codex_gate["run"].split()
    )


def test_the_marker_matches_the_one_the_tests_skip_with() -> None:
    """The workflow flag and the skip reason share one string (smoke_skip_policy owns it)."""
    sys.path.insert(0, str(REPO_ROOT / "tests" / "e2e"))
    try:
        import smoke_skip_policy
    finally:
        sys.path.remove(str(REPO_ROOT / "tests" / "e2e"))

    assert smoke_skip_policy.QUOTA_SKIP_MARKER == QUOTA_SKIP_MARKER


@pytest.mark.parametrize("cli", CLIS)
def test_plugin_load_gate_matches_its_file(smoke_job: dict[str, Any], cli: str) -> None:
    """Edge: the plugin-load gate filters on the plugin-load smoke module."""
    arguments = _gate_arguments(_step_by_name(smoke_job, PLUGIN_GATE[cli]))

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


def test_every_job_has_a_timeout(workflow_doc: dict[Any, Any]) -> None:
    """Gate 2: no job can hang to the 360 minute default."""
    expected = {
        "changes": 5,
        "authorize": 5,
        "smoke": 20,
        "smoke-codex": 20,
        "smoke-result": 5,
    }
    assert {name: job.get("timeout-minutes") for name, job in workflow_doc["jobs"].items()} == (
        expected
    )


def test_every_uv_run_is_frozen(workflow_doc: dict[Any, Any]) -> None:
    """Gate 2: CI must not re-resolve the lockfile."""
    seen = 0
    for name, job in workflow_doc["jobs"].items():
        for step in job["steps"]:
            run = str(step.get("run", ""))
            seen += run.count("uv run")
            assert run.count("uv run") == run.count("uv run --frozen"), (name, step.get("name"))
    assert seen >= 5, "the workflow lost its uv run steps; this guard would pass vacuously"


def test_result_job_hardens_the_runner(workflow_doc: dict[Any, Any]) -> None:
    """Gate 4: the Linux result job gets the same pinned harden-runner in audit mode."""
    first = workflow_doc["jobs"]["smoke-result"]["steps"][0]

    assert first["uses"].startswith("step-security/harden-runner@")
    assert re.fullmatch(r"step-security/harden-runner@[0-9a-f]{40}", first["uses"])
    assert first["with"]["egress-policy"] == "audit"


@pytest.mark.parametrize("cli", ("claude", "copilot"))
def test_prompt_based_gates_record_the_quota_skip_count(
    smoke_job: dict[str, Any], cli: str
) -> None:
    """Gate 6: every gate that allows QUOTA_SKIP: also writes the per-leg count file."""
    for step in smoke_job["steps"]:
        name = str(step.get("name", ""))
        if name.startswith("Assert the ") and f"({cli})" in name:
            arguments = _gate_arguments(step)
            assert "--allow-skip-marker" in arguments, name
            assert arguments[arguments.index("--skip-count-file") + 1] == "quota-skips.txt", name


def test_result_job_downloads_and_sums_the_quota_skip_counts(
    workflow_doc: dict[Any, Any], smoke_job: dict[str, Any]
) -> None:
    """Gate 6: leg artifacts upload, the result job downloads them and prints the count."""
    upload = _step_by_name(smoke_job, "Upload quota-skip count")
    assert upload["with"]["name"] == "quota-skips-${{ matrix.cli }}-${{ matrix.os }}"
    assert upload["with"]["path"] == "quota-skips.txt"
    assert "always()" in upload["if"]
    assert re.search(r"@[0-9a-f]{40}$", upload["uses"].split()[0])

    steps = workflow_doc["jobs"]["smoke-result"]["steps"]
    download = _step_by_name({"steps": steps}, "Download quota-skip counts")
    assert download["with"]["pattern"] == "quota-skips-*"
    assert download["with"]["path"] == "quota-skips"
    assert re.search(r"@[0-9a-f]{40}$", download["uses"].split()[0])
    report = _step_by_name({"steps": steps}, "Report")["run"]
    assert "--count-dir quota-skips" in report
    assert "{count} prompt checks quota-skipped" in report
