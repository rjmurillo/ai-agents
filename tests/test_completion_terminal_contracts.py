"""Static and registration tests for the task-completion contract (issue #5404).

This change makes two kinds of claim, graded in two places, mirroring the
pattern in ``test_orchestrator_shared_contracts.py``.

Static contract claims, graded here: ``builder-ethos.md`` carries the Task
Completion Contract (terminal predicate, precedence, reactivation) and
``voice.md`` carries the Completion-Tail Audit, on every generated surface;
the critic and QA agents no longer carry a manufactured-finding quota, on
every generated and hand-maintained surface.

Behavioral claims, graded by the eval harness: whether critic and QA approve
a genuinely complete artifact without inventing a finding, and whether the
orchestrator stops delegating once a task is terminal even with budget left.
A pytest process runs no model, so it cannot observe any of those. Those
scenarios live in ``tests/evals/critic-scenarios.json`` (``TC-1``),
``tests/evals/qa-scenarios.json`` (``S3``), and
``tests/evals/orchestrator-scenarios.json`` (``S8``), scored by::

    python3 scripts/eval/eval-prompt-change.py \
        --prompt .claude/agents/critic.md \
        --scenarios tests/evals/critic-scenarios.json

The registration tests below assert those scenarios stay present and stay
tied to the prompt text, so deleting the graded coverage fails a test
instead of passing quietly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

BUILDER_ETHOS_PATHS = (
    Path(".claude/rules/builder-ethos.md"),
    Path(".github/instructions/builder-ethos.instructions.md"),
    Path("src/copilot-cli/instructions/builder-ethos.instructions.md"),
)

VOICE_PATHS = (
    Path(".claude/rules/voice.md"),
    Path(".github/instructions/voice.instructions.md"),
    Path("src/copilot-cli/instructions/voice.instructions.md"),
)

CRITIC_PATHS = (
    Path("templates/agents/critic.shared.md"),
    Path("src/claude/critic.md"),
    Path(".claude/agents/critic.md"),
    Path(".github/agents/critic.agent.md"),
    Path("src/copilot-cli/agents/critic.agent.md"),
    Path("src/vs-code-agents/critic.agent.md"),
)

QA_PATHS = (
    Path("templates/agents/qa.shared.md"),
    Path("src/claude/qa.md"),
    Path(".claude/agents/qa.md"),
    Path(".github/agents/qa.agent.md"),
    Path("src/copilot-cli/agents/qa.agent.md"),
    Path("src/vs-code-agents/qa.agent.md"),
)

QUOTA_PHRASE = "Find at least three issues."
EXHAUSTIVE_PHRASE = "Inspect exhaustively; do not manufacture a quota."

TERMINAL_CONTRACT_PHRASES = (
    "## 4. Task Completion Contract",
    "### Terminal predicate",
    "### Reactivation",
    "frozen task contract",
)

COMPLETION_TAIL_PHRASES = (
    "## Completion-Tail Audit",
    "Want me to ...?",
    "no opt-in continuation edge",
)

CRITIC_SCENARIOS_PATH = Path("tests/evals/critic-scenarios.json")
QA_SCENARIOS_PATH = Path("tests/evals/qa-scenarios.json")
ORCHESTRATOR_SCENARIOS_PATH = Path("tests/evals/orchestrator-scenarios.json")


def _text(path: Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _scenario(payload_path: Path, scenario_id: str) -> dict[str, Any]:
    payload = json.loads((REPO_ROOT / payload_path).read_text(encoding="utf-8"))
    matches = [s for s in payload["scenarios"] if s["id"] == scenario_id]
    assert len(matches) == 1, (
        f"{payload_path} must carry exactly one scenario {scenario_id!r}; "
        f"found {len(matches)}. This scenario is the graded evidence for the "
        f"behavior; removing it leaves the acceptance criterion unmeasured."
    )
    return matches[0]


@pytest.mark.parametrize("path", BUILDER_ETHOS_PATHS, ids=str)
def test_builder_ethos_carries_the_terminal_contract(path: Path) -> None:
    text = _text(path)
    for phrase in TERMINAL_CONTRACT_PHRASES:
        assert phrase in text, f"{path} is missing {phrase!r}"


@pytest.mark.parametrize("path", VOICE_PATHS, ids=str)
def test_voice_carries_the_completion_tail_audit(path: Path) -> None:
    text = _text(path)
    for phrase in COMPLETION_TAIL_PHRASES:
        assert phrase in text, f"{path} is missing {phrase!r}"


@pytest.mark.parametrize("path", CRITIC_PATHS, ids=str)
def test_critic_has_no_manufactured_finding_quota(path: Path) -> None:
    text = _text(path)
    assert QUOTA_PHRASE not in text, (
        f"{path} still carries the manufactured-finding quota {QUOTA_PHRASE!r}"
    )
    assert EXHAUSTIVE_PHRASE in text, f"{path} is missing {EXHAUSTIVE_PHRASE!r}"


@pytest.mark.parametrize("path", QA_PATHS, ids=str)
def test_qa_has_no_manufactured_finding_quota(path: Path) -> None:
    text = _text(path)
    assert QUOTA_PHRASE not in text, (
        f"{path} still carries the manufactured-finding quota {QUOTA_PHRASE!r}"
    )
    assert EXHAUSTIVE_PHRASE in text, f"{path} is missing {EXHAUSTIVE_PHRASE!r}"


def test_critic_zero_finding_scenario_is_graded_by_the_eval_harness() -> None:
    scenario = _scenario(CRITIC_SCENARIOS_PATH, "TC-1")

    assert scenario["expected_verdict"] == "APPROVE"
    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert "CHALLENGE" in scenario["verdict_options"]


def test_qa_zero_finding_scenario_is_graded_by_the_eval_harness() -> None:
    scenario = _scenario(QA_SCENARIOS_PATH, "S3")

    assert scenario["expected_verdict"] == "PASS"
    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert "FAIL" in scenario["verdict_options"]


def test_orchestrator_budget_conservation_scenario_is_graded_by_the_eval_harness() -> None:
    scenario = _scenario(ORCHESTRATOR_SCENARIOS_PATH, "S8")

    assert scenario["expected_verdict"] == "STOP"
    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert "CONTINUE" in scenario["verdict_options"]
    assert "4 of 15 available delegations" in scenario["input"]


@pytest.mark.parametrize(
    ("scenarios_path", "scenario_id", "surface_paths"),
    [
        (CRITIC_SCENARIOS_PATH, "TC-1", CRITIC_PATHS),
        (QA_SCENARIOS_PATH, "S3", QA_PATHS),
    ],
    ids=["critic-TC-1", "qa-S3"],
)
def test_zero_finding_scenarios_stay_tied_to_the_prompt_text(
    scenarios_path: Path, scenario_id: str, surface_paths: tuple[Path, ...]
) -> None:
    """A scenario that drifts from the shipped rule would grade the wrong behavior."""
    scenario = _scenario(scenarios_path, scenario_id)

    for path in surface_paths:
        text = _text(path)
        assert EXHAUSTIVE_PHRASE in text, (
            f"{path} no longer contains {EXHAUSTIVE_PHRASE!r}, which "
            f"{scenarios_path} scenario {scenario_id!r} grades against"
        )


def test_orchestrator_budget_scenario_stays_tied_to_the_prompt_text() -> None:
    scenario = _scenario(ORCHESTRATOR_SCENARIOS_PATH, "S8")
    text = _text(Path("templates/agents/orchestrator.shared.md"))

    assert "terminal predicate" in text.lower(), (
        "templates/agents/orchestrator.shared.md no longer names the terminal "
        f"predicate, which orchestrator-scenarios.json scenario "
        f"{scenario['id']!r} grades against"
    )
