"""Gate wiring tests for the PR-gated CLI smoke workflow.

Every gate stays strict: the quota-skip marker belonged to the Claude and Copilot
prompt legs, which were deleted, so no gate allows a skip.
"""

from __future__ import annotations

from typing import Any

import yaml

from tests.lib.cli_smoke_workflow import (
    SMOKE_FILES,
    _collected_count,
    _expected_count,
    _run_commands,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


def _option_values(arguments: list[str], option: str) -> list[str]:
    return [arguments[i + 1] for i, value in enumerate(arguments) if value == option]


def test_no_gate_allows_a_quota_skip(workflow_doc: dict[Any, Any]) -> None:
    """Negative: with no prompt-based leg, a skip must fail the gate (comments excluded)."""
    text = yaml.safe_dump(workflow_doc)

    assert "--allow-skip-marker" not in text
    assert "QUOTA_SKIP" not in text


def test_codex_gate_stays_strict(codex_job: dict[str, Any]) -> None:
    """Negative: the Codex gate allows no skip and requires both load tests to pass."""
    gate = _step_by_name(codex_job, "Assert the plugin-load smoke actually ran")
    gate_run = " ".join(gate["run"].split())

    assert "--allow-skip-marker" not in gate_run
    assert "--require-pass test_codex_plugin_loads_expected_skills" in gate_run
    assert "--require-pass test_codex_agents_install_and_load" in gate_run


def test_hook_discovery_gate_stays_strict_and_matches_its_file(hooks_job: dict[str, Any]) -> None:
    """Edge: the gate filters on its own module and demands every test the marker selects."""
    gate = _step_by_name(hooks_job, "Assert the hook discovery smoke actually ran")
    arguments = _run_commands(gate)[0]

    assert "always()" in gate["if"]
    assert "--allow-skip-marker" not in arguments
    assert _option_values(arguments, "--smoke-substr") == ["test_claude_hook_discovery_smoke"]
    assert _expected_count(gate) == _collected_count(SMOKE_FILES["hook-discovery"], "claude")
    assert len(_option_values(arguments, "--require-pass")) == _expected_count(gate)
