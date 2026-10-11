"""Provider-secret and Codex job tests for the CLI smoke workflow (REQ-047 AC3, AC9, AC11).

Only agent environments read provider secrets. The Codex job reads none and
runs in no environment.
"""

from __future__ import annotations

import shlex
from typing import Any

import yaml

from tests.lib.cli_smoke_workflow import (
    EVERY_MODEL_SECRET,
    OPERATING_SYSTEMS,
    SEMVER,
    SMOKE_FILES,
    _collected_count,
    _expected_count,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


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
