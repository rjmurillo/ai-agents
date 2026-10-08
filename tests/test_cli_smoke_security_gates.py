"""Gate wiring tests for the PR-gated CLI smoke workflow.

The prompt-based gates allow the quota-skip marker, and the zero-token load
test must still pass. The strict gates stay strict.
"""

from __future__ import annotations

import re
import sys
from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    CLIS,
    HOOK_GATE,
    PLUGIN_GATE,
    REPO_ROOT,
    SMOKE_FILES,
    _collected_count,
    _expected_count,
    _run_commands,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


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
    arguments = _run_commands(_step_by_name(smoke_job, gates[cli]))[0]

    assert _option_values(arguments, "--allow-skip-marker") == [QUOTA_SKIP_MARKER]


@pytest.mark.parametrize("cli", CLIS)
def test_plugin_load_gate_requires_the_zero_token_test_to_pass(
    smoke_job: dict[str, Any], cli: str
) -> None:
    """The zero-token load test must PASS, so a quota skip cannot make the leg green."""
    arguments = _run_commands(_step_by_name(smoke_job, PLUGIN_GATE[cli]))[0]

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
