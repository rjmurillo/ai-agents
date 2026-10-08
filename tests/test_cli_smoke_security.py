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

import ast
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
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml"
RENOVATE_CONFIG = REPO_ROOT / "renovate.json"
CLIS = ("claude", "copilot")
# Claude legs use the subscription OAuth token (REQ-047 owner decision); the API
# key ran out of credit on 2026-10-07 and must not be read by the smoke.
CLI_SECRET = {"claude": "CLAUDE_CODE_OAUTH_TOKEN", "copilot": "COPILOT_GITHUB_TOKEN"}
SECRET_NAMES = set(CLI_SECRET.values())
EVERY_MODEL_SECRET = SECRET_NAMES | {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FACTORY_API_KEY"}
CLI_PACKAGE = {"claude": "@anthropic-ai/claude-code", "copilot": "@github/copilot"}
PACKAGE_VERSION_ENV = {
    "@anthropic-ai/claude-code": "CLAUDE_CODE_VERSION",
    "@github/copilot": "COPILOT_CLI_VERSION",
    "@openai/codex": "CODEX_CLI_VERSION",
}
OPERATING_SYSTEMS = ["ubuntu-latest", "macos-latest", "windows-latest"]
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
def workflow_doc() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def smoke_job(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    return workflow_doc["jobs"]["smoke"]


@pytest.fixture(scope="module")
def codex_job(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    return workflow_doc["jobs"]["smoke-codex"]


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
            sys.executable,
            "-m",
            "pytest",
            test_file,
            "-m",
            f"smoke and {cli}",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # Exit 5 means "no tests collected", which is a valid count of zero.
    assert result.returncode in (0, 5), result.stdout + result.stderr
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


def _expected_count(step: dict[str, Any]) -> int:
    arguments = shlex.split(step["run"])
    assert arguments.count("--expected-count") == 1
    return int(arguments[arguments.index("--expected-count") + 1])


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
    """The workflow flag and the skip reason share one string (probe module owns it)."""
    sys.path.insert(0, str(REPO_ROOT / "tests" / "e2e"))
    try:
        import copilot_hook_probe
    finally:
        sys.path.remove(str(REPO_ROOT / "tests" / "e2e"))

    assert copilot_hook_probe.QUOTA_SKIP_MARKER == QUOTA_SKIP_MARKER


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


# ---------------------------------------------------------------------------
# Triggers, trust gate, and fork denial (REQ-047 AC12)
# ---------------------------------------------------------------------------


def _triggers(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML parses the bare key `on` as boolean True.
    return workflow_doc.get(True) or workflow_doc.get("on")


def test_workflow_triggers_on_pull_request_and_dispatch_only(
    workflow_doc: dict[Any, Any],
) -> None:
    """Positive and negative: the nightly schedule is gone, no privileged trigger exists."""
    triggers = _triggers(workflow_doc)

    assert set(triggers) == {"pull_request", "workflow_dispatch"}
    assert set(triggers["pull_request"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    }
    assert "pull_request_target" not in triggers
    assert "schedule" not in triggers


def test_runs_are_cancelled_per_pull_request(workflow_doc: dict[Any, Any]) -> None:
    concurrency = workflow_doc["concurrency"]

    assert concurrency["cancel-in-progress"] is True
    assert "github.event.pull_request.number" in concurrency["group"]


def test_top_level_permissions_are_read_only(workflow_doc: dict[Any, Any]) -> None:
    assert workflow_doc["permissions"] == {"contents": "read"}
    for name, job in workflow_doc["jobs"].items():
        assert job["permissions"] == {"contents": "read"}, name


def test_trust_gate_receives_the_head_repository(workflow_doc: dict[Any, Any]) -> None:
    """Positive: a fork PR is told apart from a same-repo PR by its head repository."""
    gate = _step_by_name(workflow_doc["jobs"]["authorize"], "Check trusted context")

    assert gate["env"]["HEAD_REPOSITORY"] == "${{ github.event.pull_request.head.repo.full_name }}"
    assert '--head-repository "$HEAD_REPOSITORY"' in gate["run"]
    assert "assert_trusted_smoke_context.py" in gate["run"]


@pytest.mark.parametrize("job_name", ["smoke", "smoke-codex"])
def test_legs_wait_for_the_filter_and_the_trust_gate(
    workflow_doc: dict[Any, Any], job_name: str
) -> None:
    """Negative: no leg can start without a positive path decision and a trusted context."""
    job = workflow_doc["jobs"][job_name]

    assert set(job["needs"]) == {"changes", "authorize"}
    assert "needs.changes.outputs.run == 'true'" in job["if"]
    assert "needs.authorize.outputs.trusted == 'true'" in job["if"]


def test_path_filter_diffs_with_full_history_through_the_python_cli(
    workflow_doc: dict[Any, Any],
) -> None:
    job = workflow_doc["jobs"]["changes"]
    checkout = next(step for step in job["steps"] if "actions/checkout" in step.get("uses", ""))
    filter_step = _step_by_name(job, "Decide whether the smoke must run")

    assert checkout["with"]["fetch-depth"] == 0
    assert "scripts/validation/cli_smoke_paths.py" in filter_step["run"]
    assert filter_step["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert filter_step["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert job["outputs"]["run"] == "${{ steps.filter.outputs.run }}"


BASE_CHECKOUT_PATH = "trusted-base"
FILTER_SCRIPT = "scripts/validation/cli_smoke_paths.py"


def _checkouts(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if "actions/checkout" in step.get("uses", "")]


def test_path_filter_script_comes_from_the_base_commit(workflow_doc: dict[Any, Any]) -> None:
    """REQ-047 AC12: a fork PR cannot edit the filter to return run=false.

    The script is checked out from the pull request base SHA into its own
    directory and executed from there with isolated mode (``-I``), so a
    ``sitecustomize.py`` or a ``PYTHONPATH`` shadow in the PR tree cannot run.
    """
    job = workflow_doc["jobs"]["changes"]
    base_checkout = next(c for c in _checkouts(job) if c.get("with", {}).get("path"))
    steps = job["steps"]
    filter_step = _step_by_name(job, "Decide whether the smoke must run")
    arguments = shlex.split(filter_step["run"])

    assert "github.event.pull_request.base.sha" in base_checkout["with"]["ref"]
    assert base_checkout["with"]["path"] == BASE_CHECKOUT_PATH
    assert base_checkout["with"]["persist-credentials"] is False
    assert FILTER_SCRIPT in base_checkout["with"]["sparse-checkout"]
    assert steps.index(base_checkout) < steps.index(filter_step)
    assert arguments[:3] == ["python3", "-I", f"{BASE_CHECKOUT_PATH}/{FILTER_SCRIPT}"]


def test_path_filter_diffs_the_pull_request_tree_not_the_base_copy(
    workflow_doc: dict[Any, Any],
) -> None:
    """Edge: the base copy only supplies code; git diff runs in the PR checkout."""
    job = workflow_doc["jobs"]["changes"]
    pr_checkout = next(c for c in _checkouts(job) if not c.get("with", {}).get("path"))
    arguments = shlex.split(_step_by_name(job, "Decide whether the smoke must run")["run"])

    assert pr_checkout["with"]["fetch-depth"] == 0
    assert arguments[arguments.index("--repo-root") + 1] == "$GITHUB_WORKSPACE"


def test_no_step_runs_the_filter_from_the_pull_request_tree(
    workflow_doc: dict[Any, Any],
) -> None:
    """Negative: every execution of the filter goes through the base copy."""
    for job_name, job in workflow_doc["jobs"].items():
        for step in job["steps"]:
            for line in str(step.get("run", "")).splitlines():
                if FILTER_SCRIPT not in line or "python" not in line:
                    continue
                assert f"{BASE_CHECKOUT_PATH}/{FILTER_SCRIPT}" in line, (job_name, line)


# ---------------------------------------------------------------------------
# Provider secrets (REQ-047 AC3, AC9)
# ---------------------------------------------------------------------------


def test_only_copilot_steps_read_the_copilot_token(workflow_doc: dict[Any, Any]) -> None:
    """REQ-047 AC3: the Copilot token is read by Copilot smoke steps and nothing else."""
    readers = [
        (job_name, step["name"])
        for job_name, job in workflow_doc["jobs"].items()
        for step in job["steps"]
        if "secrets.COPILOT_GITHUB_TOKEN" in str(step.get("env"))
    ]

    assert readers == [
        ("smoke", "Run real-CLI hook smoke (copilot)"),
        ("smoke", "Run real-CLI plugin-load smoke (copilot)"),
    ]


def test_no_job_reads_the_anthropic_api_key(workflow_doc: dict[Any, Any]) -> None:
    """Negative: the Claude smoke uses the subscription token, never the exhausted API key."""
    assert "secrets.ANTHROPIC_API_KEY" not in yaml.safe_dump(workflow_doc)


def test_every_secret_reader_sits_in_an_agent_environment(
    workflow_doc: dict[Any, Any],
) -> None:
    for name, job in workflow_doc["jobs"].items():
        if "secrets." in yaml.safe_dump(job):
            assert job.get("environment") == "agent-${{ matrix.cli }}", name


# ---------------------------------------------------------------------------
# Codex job: no environment, no secret (REQ-047 AC11)
# ---------------------------------------------------------------------------


def test_codex_job_has_no_environment_and_reads_no_secret(codex_job: dict[str, Any]) -> None:
    """Negative: the credential-free leg cannot be handed a provider key."""
    dumped = yaml.safe_dump(codex_job)

    assert "environment" not in codex_job
    assert "secrets." not in dumped
    for name in EVERY_MODEL_SECRET:
        assert name not in dumped


def test_codex_job_matrix_covers_each_operating_system(codex_job: dict[str, Any]) -> None:
    matrix = codex_job["strategy"]["matrix"]

    assert matrix["os"] == OPERATING_SYSTEMS
    assert "cli" not in matrix
    assert codex_job["strategy"]["fail-fast"] is False


def test_codex_install_uses_the_exact_pinned_version(codex_job: dict[str, Any]) -> None:
    install = _step_by_name(codex_job, "Install pinned Codex CLI")

    assert SEMVER.fullmatch(codex_job["env"]["CODEX_CLI_VERSION"])
    assert '"@openai/codex@${CODEX_CLI_VERSION}"' in install["run"]
    assert not (install.get("env") or {})


def test_codex_step_selects_only_the_codex_marker(codex_job: dict[str, Any]) -> None:
    run = _step_by_name(codex_job, "Run real-CLI plugin-load smoke (codex)")
    arguments = shlex.split(run["run"])

    assert arguments[arguments.index("-m") + 1] == "smoke and codex"
    assert "tests/e2e/test_plugin_load_smoke.py" in arguments
    assert not (run.get("env") or {})


def test_codex_expected_count_matches_the_collected_smoke_tests(
    codex_job: dict[str, Any],
) -> None:
    gate = _step_by_name(codex_job, "Assert the plugin-load smoke actually ran")

    assert "always()" in gate["if"]
    assert _expected_count(gate) == _collected_count(SMOKE_FILES["plugin"], "codex")
    assert _collected_count(SMOKE_FILES["hook"], "codex") == 0


# ---------------------------------------------------------------------------
# Result job: the one required check
# ---------------------------------------------------------------------------


def test_result_job_always_runs_and_waits_for_every_other_job(
    workflow_doc: dict[Any, Any],
) -> None:
    result = workflow_doc["jobs"]["smoke-result"]

    assert result["name"] == "CLI Smoke Result"
    assert result["if"] == "${{ !cancelled() }}"
    assert set(result["needs"]) == {"changes", "authorize", "smoke", "smoke-codex"}
    assert "environment" not in result


def test_result_job_checks_every_leg_and_names_the_fork(workflow_doc: dict[Any, Any]) -> None:
    """REQ-047 AC6, AC12: any skipped, cancelled, or failed leg turns the gate red."""
    report = _step_by_name(workflow_doc["jobs"]["smoke-result"], "Report")
    env = report["env"]

    for variable, job in [
        ("CHANGES_RESULT", "changes"),
        ("AUTHORIZE_RESULT", "authorize"),
        ("SMOKE_RESULT", "smoke"),
        ("CODEX_RESULT", "smoke-codex"),
    ]:
        assert env[variable] == f"${{{{ needs.{job}.result }}}}"
        assert f"{variable} success" in report["run"]
    assert env["TRUSTED"] == "${{ needs.authorize.outputs.trusted }}"
    assert env["RUN"] == "${{ needs.changes.outputs.run }}"
    assert "--skip-when RUN false" in report["run"]
    assert "TRUSTED true" in report["run"]
    assert "fork pull request" in report["run"]
    assert "require_job_results.py" in report["run"]


def test_result_job_filter_failure_is_not_skippable(workflow_doc: dict[Any, Any]) -> None:
    """Negative: a broken path filter must fail the gate, not read as 'nothing to run'."""
    run = _step_by_name(workflow_doc["jobs"]["smoke-result"], "Report")["run"]

    assert "--check CHANGES_RESULT success" in " ".join(run.split())


def test_nightly_workflow_is_removed() -> None:
    assert not (REPO_ROOT / ".github" / "workflows" / "nightly-cli-smoke.yml").exists()


# ---------------------------------------------------------------------------
# Trusted scripts and checkout hygiene
# ---------------------------------------------------------------------------

TRUSTED_SCRIPTS = (
    "assert_trusted_smoke_context.py",
    "require_job_results.py",
    "assert_smoke_ran.py",
)


def _run_lines(workflow_doc: dict[Any, Any]) -> list[tuple[str, str]]:
    return [
        (job_name, line)
        for job_name, job in workflow_doc["jobs"].items()
        for step in job["steps"]
        for line in str(step.get("run", "")).splitlines()
    ]


@pytest.mark.parametrize("script", TRUSTED_SCRIPTS)
def test_trusted_scripts_run_only_from_the_base_checkout_in_isolated_mode(
    workflow_doc: dict[Any, Any], script: str
) -> None:
    """P1: a pull request cannot edit the gate that judges it."""
    invocations = [
        (job, line) for job, line in _run_lines(workflow_doc) if script in line
    ]

    assert invocations, script
    for job, line in invocations:
        match = re.search(r"(?:^|[\s(])python3? -I (\S+)", line)
        assert match is not None, (job, line)
        assert match.group(1).startswith(f"{BASE_CHECKOUT_PATH}/"), (job, line)
        assert "uv run" not in line, (job, line)


@pytest.mark.parametrize("script", TRUSTED_SCRIPTS)
def test_every_job_that_runs_a_trusted_script_checks_it_out_from_the_base(
    workflow_doc: dict[Any, Any], script: str
) -> None:
    for job_name, job in workflow_doc["jobs"].items():
        runs_it = any(script in str(step.get("run", "")) for step in job["steps"])
        if not runs_it:
            continue
        bases = [
            c["with"]
            for c in _checkouts(job)
            if c.get("with", {}).get("path") == BASE_CHECKOUT_PATH
        ]
        assert any(
            "github.event.pull_request.base.sha" in b["ref"] and script in b["sparse-checkout"]
            for b in bases
        ), (job_name, script)


@pytest.mark.parametrize("script", TRUSTED_SCRIPTS)
def test_trusted_scripts_import_only_the_standard_library(script: str) -> None:
    """`python -I` runs without the project environment, so third-party imports break."""
    path = next(REPO_ROOT.glob(f"scripts/**/{script}"))
    modules = {
        node.module.split(".")[0] if isinstance(node, ast.ImportFrom) else alias.name.split(".")[0]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
        if not (isinstance(node, ast.ImportFrom) and node.level)
    }

    assert modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names)


def test_every_checkout_drops_persisted_credentials(workflow_doc: dict[Any, Any]) -> None:
    """P2: no later step in a job can reuse the checkout token."""
    checkouts = [c for job in workflow_doc["jobs"].values() for c in _checkouts(job)]

    assert checkouts
    for checkout in checkouts:
        assert checkout.get("with", {}).get("persist-credentials") is False, checkout
