"""Cross-harness contract tests for orchestrator context and output behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

ORCHESTRATOR_PATHS = (
    Path("templates/agents/orchestrator.shared.md"),
    Path("src/claude/orchestrator.md"),
    Path(".claude/agents/orchestrator.md"),
    Path(".github/agents/orchestrator.agent.md"),
    Path("src/copilot-cli/agents/orchestrator.agent.md"),
    Path("src/vs-code-agents/orchestrator.agent.md"),
)

COPILOT_PROMPT_PATHS = (
    Path(".github/agents/orchestrator.agent.md"),
    Path("src/copilot-cli/agents/orchestrator.agent.md"),
)

SCENARIOS_PATH = (
    REPO_ROOT / "tests" / "eval_scenarios" / "orchestrator_shared_contracts.json"
)

CONTEXT_HEADING = "## Context Maintenance"
OUTPUT_HEADING = "## Output Bounds"
COPILOT_PROMPT_LIMIT = 30_000


def _section(path: Path, heading: str) -> str:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    start = text.find(heading)
    assert start != -1, f"{path} is missing {heading!r}"
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_each_surface_carries_both_shared_contracts(path: Path) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    assert text.count(CONTEXT_HEADING) == 1
    assert text.count(OUTPUT_HEADING) == 1


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_context_section_carries_continuation_contract(path: Path) -> None:
    section = _section(path, CONTEXT_HEADING)

    for phrase in (
        "Continue, do not restart.",
        "Never repeat completed phases.",
        "Do not re-ask answered questions.",
        "Do not re-delegate unchanged work.",
        "Preserve work across compaction.",
    ):
        assert phrase in section


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_output_section_carries_synthesis_bounds(path: Path) -> None:
    section = _section(path, OUTPUT_HEADING)

    assert "400 words or 4 paragraphs, whichever comes first" in section
    assert "cut the weakest finding" in section


def test_behavioral_scenarios_cover_both_contracts() -> None:
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    scenarios = {scenario["id"]: scenario for scenario in data["scenarios"]}

    assert set(scenarios) == {"context-active-phase", "bounded-synthesis"}
    assert scenarios["context-active-phase"]["expected_verdict"] == (
        "CONTINUE_ACTIVE_PHASE"
    )
    assert scenarios["bounded-synthesis"]["expected_verdict"] == "BOUND_SYNTHESIS"
    for scenario in scenarios.values():
        assert scenario["expected_verdict"] in scenario["verdict_options"]
        assert scenario["expected_reason_contains"]


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_shared_contracts_do_not_leak_adapter_syntax(path: Path) -> None:
    sections = _section(path, CONTEXT_HEADING) + _section(path, OUTPUT_HEADING)

    for adapter_token in ("mcp__", "serena/", "#runSubagent", "/agent", "Task("):
        assert adapter_token not in sections


@pytest.mark.parametrize("path", COPILOT_PROMPT_PATHS, ids=str)
def test_copilot_prompt_stays_below_host_limit(path: Path) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    assert len(text) < COPILOT_PROMPT_LIMIT, (
        f"{path} is {len(text)} characters; limit is {COPILOT_PROMPT_LIMIT}"
    )
