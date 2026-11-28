"""Gate ordering, hardening, and result-job tests for the CLI smoke workflow.

Gates run after a failed smoke, every job has a timeout, every ``uv run`` is
frozen, and the result job has no quota-skip plumbing.
"""

from __future__ import annotations

import re
from typing import Any

from scripts.validation.smoke_result import PRESETS
from tests.lib.cli_smoke_workflow import (
    _run_commands,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


def test_plugin_load_gate_matches_its_file(codex_job: dict[str, Any]) -> None:
    """Edge: the plugin-load gate filters on the plugin-load smoke module."""
    gate = _step_by_name(codex_job, "Assert the plugin-load smoke actually ran")
    arguments = _run_commands(gate)[0]

    assert arguments.count("--smoke-substr") == 1
    assert arguments[arguments.index("--smoke-substr") + 1] == "test_plugin_load_smoke"


def test_gates_still_run_after_a_failed_smoke(workflow_doc: dict[Any, Any]) -> None:
    """Edge: every assert step keeps always(), so a skip still turns the leg red."""
    gates = 0
    for name, job in workflow_doc["jobs"].items():
        for step in job["steps"]:
            if str(step.get("name", "")).startswith("Assert the "):
                gates += 1
                assert "always()" in step["if"], (name, step["name"])
    assert gates == 3, "one gate per CLI leg; the guard would pass vacuously otherwise"


def test_every_job_has_a_timeout(workflow_doc: dict[Any, Any]) -> None:
    """Gate 2: no job can hang to the 360 minute default."""
    expected = {
        "changes": 5,
        "authorize": 5,
        "smoke-codex": 20,
        "smoke-claude-hooks": 20,
        "smoke-pi": 20,
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
    assert seen >= 3, "the workflow lost its uv run steps; this guard would pass vacuously"


def test_result_job_hardens_the_runner(workflow_doc: dict[Any, Any]) -> None:
    """Gate 4: the Linux result job gets the same pinned harden-runner in audit mode."""
    first = workflow_doc["jobs"]["smoke-result"]["steps"][0]

    assert first["uses"].startswith("step-security/harden-runner@")
    assert re.fullmatch(r"step-security/harden-runner@[0-9a-f]{40}", first["uses"])
    assert first["with"]["egress-policy"] == "audit"


def test_result_job_has_no_quota_skip_plumbing(workflow_doc: dict[Any, Any]) -> None:
    """Negative: the quota-skip artifacts came from the deleted prompt legs."""
    names = {step.get("name") for job in workflow_doc["jobs"].values() for step in job["steps"]}

    assert "Upload quota-skip count" not in names
    assert "Download quota-skip counts" not in names
    argv = " ".join(PRESETS["plugin-cli-smoke"])
    assert "--count-dir" not in argv
    assert "quota-skipped" not in argv
    report = _step_by_name(workflow_doc["jobs"]["smoke-result"], "Report")["run"]
    assert report.strip().endswith("smoke_result.py --preset plugin-cli-smoke")
