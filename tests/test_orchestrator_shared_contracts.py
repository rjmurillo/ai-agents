"""Cross-harness contract tests for orchestrator context and output behavior.

This change makes two kinds of claim, and they are graded in two places.

Static contract claims, graded here: every orchestrator surface carries the same
Context Maintenance and Output Bounds text, that text leaks no adapter syntax,
and both Copilot prompts stay under the host character limit. Those are
properties of the shipped files, so reading the files is the strongest evidence
they admit.

Behavioral claims, graded by the eval harness: whether a model continues an
active phase instead of restarting or re-asking, and whether it caps an
oversized synthesis at the stated bound. A pytest process runs no model, so it
cannot observe either. Those scenarios live in
``tests/evals/orchestrator-scenarios.json`` as ``S6`` and ``S7`` and are scored
by the repository's prompt-change evaluator::

    python3 scripts/eval/eval-prompt-change.py \
        --prompt .claude/agents/orchestrator.md \
        --scenarios tests/evals/orchestrator-scenarios.json

The registration tests below assert those scenarios stay present and stay tied
to the prompt text, so deleting the graded coverage fails a test instead of
passing quietly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

BEHAVIORAL_SCENARIOS_PATH = Path("tests/evals/orchestrator-scenarios.json")
ACTIVE_PHASE_SCENARIO_ID = "S6"
SYNTHESIS_BOUND_SCENARIO_ID = "S7"

ACTIVE_PHASE_CONTRACT = (
    "Continue, do not restart.",
    "Never repeat completed phases.",
    "Do not re-ask answered questions.",
    "Do not re-delegate unchanged work.",
    "Preserve work across compaction.",
)

SYNTHESIS_BOUND_CONTRACT = (
    "400 words or 4 paragraphs, whichever comes first",
    "cut the weakest finding, not the strongest recommendation",
)


def _section(path: Path, heading: str) -> str:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    start = text.find(heading)
    assert start != -1, f"{path} is missing {heading!r}"
    rest = text[start + len(heading) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def _scenario(scenario_id: str) -> dict[str, Any]:
    payload = json.loads((REPO_ROOT / BEHAVIORAL_SCENARIOS_PATH).read_text(encoding="utf-8"))
    matches = [s for s in payload["scenarios"] if s["id"] == scenario_id]
    assert len(matches) == 1, (
        f"{BEHAVIORAL_SCENARIOS_PATH} must carry exactly one scenario {scenario_id!r}; "
        f"found {len(matches)}. This scenario is the graded evidence for the behavior; "
        f"removing it leaves the acceptance criterion unmeasured."
    )
    return matches[0]


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_each_surface_carries_both_shared_contracts(path: Path) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    assert text.count(CONTEXT_HEADING) == 1
    assert text.count(OUTPUT_HEADING) == 1


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_each_surface_states_the_active_phase_contract(path: Path) -> None:
    """Static check: the continuation rules are present and worded identically."""
    section = _section(path, CONTEXT_HEADING)

    for phrase in ACTIVE_PHASE_CONTRACT:
        assert phrase in section, f"{path} Context Maintenance is missing {phrase!r}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_each_surface_states_the_synthesis_bound(path: Path) -> None:
    """Static check: the synthesis cap and the trim rule are present."""
    section = _section(path, OUTPUT_HEADING)

    for phrase in SYNTHESIS_BOUND_CONTRACT:
        assert phrase in section, f"{path} Output Bounds is missing {phrase!r}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_duplicate_routing_rule_permits_a_changed_retry(path: Path) -> None:
    """The routing rule must not forbid what Context Maintenance permits.

    Context Maintenance allows retrying a failed delegation after the approach
    or context changes. An unqualified ban on re-delegating anything routed this
    session would contradict it, because every failed delegation was routed.
    """
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    assert "Do not re-delegate work already routed this session." not in text, (
        f"{path} carries an unqualified duplicate-routing ban that contradicts "
        f"the Context Maintenance retry rule"
    )
    assert "Do not re-delegate work that is still in flight" in text
    assert "A failed delegation may be retried once you change the approach" in text


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


def test_active_phase_behavior_is_graded_by_the_eval_harness() -> None:
    """The continuation behavior is scored against a model, not asserted here."""
    scenario = _scenario(ACTIVE_PHASE_SCENARIO_ID)

    assert scenario["expected_verdict"] == "CONTINUE"
    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert "RESTART" in scenario["verdict_options"]
    assert "REASK" in scenario["verdict_options"]
    assert "phase 3 (implementer) is active" in scenario["input"].lower()
    assert "complete" in scenario["input"].lower()


def test_synthesis_bound_behavior_is_graded_by_the_eval_harness() -> None:
    """The trim behavior is scored against a model, not asserted here."""
    scenario = _scenario(SYNTHESIS_BOUND_SCENARIO_ID)

    assert scenario["expected_verdict"] == "TRIM"
    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert "FULL" in scenario["verdict_options"]
    assert "2,000-word" in scenario["input"]


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_graded_scenarios_stay_tied_to_the_prompt_text(path: Path) -> None:
    """A scenario that drifts from the shipped bound would grade the wrong rule."""
    scenario = _scenario(SYNTHESIS_BOUND_SCENARIO_ID)
    section = _section(path, OUTPUT_HEADING)

    assert scenario["expected_reason_contains"] in section, (
        f"{path} Output Bounds no longer contains "
        f"{scenario['expected_reason_contains']!r}, which "
        f"{BEHAVIORAL_SCENARIOS_PATH} grades against"
    )
