"""Regression guards for implementer `.agents/` scaffold ownership."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCENARIOS = _REPO_ROOT / "tests" / "evals" / "implementer-scenarios.json"
_IMPLEMENTER_FILES = (
    "templates/agents/implementer.shared.md",
    "src/claude/implementer.md",
    ".claude/agents/implementer.md",
    ".github/agents/implementer.agent.md",
    "src/copilot-cli/agents/implementer.agent.md",
    "src/vs-code-agents/implementer.agent.md",
)

_CONSUMER_OWNED_NOTICE = (
    "[INFO] Consumer install: consumer-owned .agents/ without ai-agents session scaffold; "
    "proceeding without session-protocol gates"
)
_TOOLKIT_SIGNAL = "If `.agents/AGENT-INSTRUCTIONS.md` exists, it is the ai-agents session scaffold"
_UNKNOWN_OWNERSHIP_BLOCK = "[BLOCKED] Cannot determine .agents scaffold ownership"
_STALE_EXISTS_ONLY_RULE = "The `.agents/` stop conditions below apply only when `.agents/` exists."


def _implementer_scenarios() -> dict[str, dict]:
    payload = json.loads(_SCENARIOS.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    return {scenario["id"]: scenario for scenario in scenarios}


def _read(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_consumer_owned_agents_directory_scenario_pins_proceed() -> None:
    """A consumer-owned `.agents/` directory is not a torn toolkit scaffold."""
    scenario = _implementer_scenarios()["S13"]

    assert scenario["expected_verdict"] == "PROCEED"
    assert "consumer-owned `.agents/tools`" in scenario["input"]
    assert ".agents/HANDOFF.md" in scenario["input"]
    assert "consumer-owned .agents" in scenario["expected_reason_contains"]


@pytest.mark.parametrize("relative_path", _IMPLEMENTER_FILES)
def test_implementer_prompts_name_consumer_owned_agents_state(
    relative_path: str,
) -> None:
    """The gate has a third state for consumer-owned `.agents/` directories."""
    text = _read(relative_path)

    assert _CONSUMER_OWNED_NOTICE in text
    assert _TOOLKIT_SIGNAL in text
    assert _STALE_EXISTS_ONLY_RULE not in text


@pytest.mark.parametrize("relative_path", _IMPLEMENTER_FILES)
def test_implementer_prompts_keep_partial_toolkit_scaffold_blocking(
    relative_path: str,
) -> None:
    """A partial toolkit scaffold still stops instead of failing open."""
    text = _read(relative_path)

    assert "stop and report `[BLOCKED] No prior session context available`" in text
    assert "stop and report `[BLOCKED] Missing root agent instructions`" in text


@pytest.mark.parametrize("relative_path", _IMPLEMENTER_FILES)
def test_implementer_prompts_block_indeterminate_scaffold_ownership(
    relative_path: str,
) -> None:
    """Cannot determine is a loud state, not a permissive default."""
    assert _UNKNOWN_OWNERSHIP_BLOCK in _read(relative_path)
