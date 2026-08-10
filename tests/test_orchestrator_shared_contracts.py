"""Cross-harness contract tests for orchestrator context and output behavior."""

from __future__ import annotations

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

CONTEXT_HEADING = "## Context Maintenance"
OUTPUT_HEADING = "## Output Bounds"
COPILOT_PROMPT_LIMIT = 30_000


@pytest.fixture
def active_phase_scenario() -> dict[str, object]:
    """Phases one and two are complete, while phase three remains active."""
    return {
        "prompt": (
            "Analyst investigation and architect review are complete. "
            "The implementer phase is active. Continue."
        ),
        "expected_outcome": "continue phase 3 without restarting or re-asking",
        "required_contract": (
            "Continue, do not restart.",
            "Never repeat completed phases.",
            "Do not re-ask answered questions.",
            "Do not re-delegate unchanged work.",
            "Preserve work across compaction.",
        ),
    }


@pytest.fixture
def oversized_synthesis_scenario() -> dict[str, object]:
    """Returned evidence exceeds the user-facing synthesis cap."""
    return {
        "prompt": "Summarize a 2,000-word investigation and completed design review.",
        "expected_outcome": "400 words or 4 paragraphs, whichever comes first",
        "required_trim": "cut the weakest finding",
    }


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
def test_active_phase_continues_without_restarting(
    path: Path,
    active_phase_scenario: dict[str, object],
) -> None:
    section = _section(path, CONTEXT_HEADING)

    assert "implementer phase is active" in str(active_phase_scenario["prompt"])
    for phrase in active_phase_scenario["required_contract"]:
        assert phrase in section


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_oversized_synthesis_uses_the_same_bounds(
    path: Path,
    oversized_synthesis_scenario: dict[str, object],
) -> None:
    section = _section(path, OUTPUT_HEADING)

    assert "2,000-word" in str(oversized_synthesis_scenario["prompt"])
    assert oversized_synthesis_scenario["expected_outcome"] in section
    assert oversized_synthesis_scenario["required_trim"] in section


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
