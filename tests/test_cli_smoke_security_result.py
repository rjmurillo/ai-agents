"""Gate ordering, hardening, and result-job tests for the CLI smoke workflow.

Gates run after a failed smoke, every job has a timeout, every ``uv run`` is
frozen, and the result job sums the quota-skip counts.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    CLIS,
    PLUGIN_GATE,
    _expected_count,
    _run_commands,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


@pytest.mark.parametrize("cli", CLIS)
def test_plugin_load_gate_matches_its_file(smoke_job: dict[str, Any], cli: str) -> None:
    """Edge: the plugin-load gate filters on the plugin-load smoke module."""
    arguments = _run_commands(_step_by_name(smoke_job, PLUGIN_GATE[cli]))[0]

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
    """Gate 6: a gate that allows QUOTA_SKIP: is followed by a report of the same report file."""
    for step in smoke_job["steps"]:
        name = str(step.get("name", ""))
        if name.startswith("Assert the ") and f"({cli})" in name:
            # shell: bash runs with -e, so a failed gate stops the step before the report.
            assert step.get("shell") == "bash", name
            gate, report = _run_commands(step)[:2]
            assert "--allow-skip-marker" in gate, name
            assert report[2] == "trusted-base/scripts/validation/smoke_quota_report.py", name
            assert report[3] == gate[3], name
            assert report[report.index("--skip-count-file") + 1] == "quota-skips.txt", name
            assert "--skip-count-file" not in gate, name
            for option in ("--allow-skip-marker", "--smoke-substr"):
                if option in gate:
                    assert report[report.index(option) + 1] == gate[gate.index(option) + 1], name


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
