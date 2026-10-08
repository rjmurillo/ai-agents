"""Trigger, trust-gate, and checkout-hygiene tests for the CLI smoke workflow.

The workflow triggers on ``pull_request``, so a fork PR must fail closed with a
message naming the fork (REQ-047 AC12). Trusted gate scripts run only from the
base checkout. Credential scope, matrix, and gate wiring live in
``tests/test_cli_smoke_security.py``; shared helpers live in
``tests/lib/cli_smoke_workflow.py``.
"""

from __future__ import annotations

import ast
import re
import shlex
import sys
from typing import Any

import pytest
import yaml

from tests.lib.cli_smoke_workflow import (
    EVERY_MODEL_SECRET,
    OPERATING_SYSTEMS,
    REPO_ROOT,
    SEMVER,
    SMOKE_FILES,
    _collected_count,
    _expected_count,
    _step_by_name,
    load_workflow,
)


@pytest.fixture(scope="module")
def workflow_doc() -> dict[Any, Any]:
    return load_workflow()


@pytest.fixture(scope="module")
def codex_job(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    return workflow_doc["jobs"]["smoke-codex"]


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
    invocations = [(job, line) for job, line in _run_lines(workflow_doc) if script in line]

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
