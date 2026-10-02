"""Static contract tests for the orchestrator Resume Check.

The Resume Check lives in Context Maintenance. These tests grade the shipped
files: every orchestrator surface carries the state record fields, the live
verification steps, and the fail-closed rules. Behavioral claims (hold on a
stale handoff, continue on a matching one, skip an already-done next action) are
graded by the eval harness through scenarios ``S17``, ``S18``, and ``S19`` in
``tests/evals/orchestrator-scenarios.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HEADING = "### Resume Check (fail closed)"
SCENARIOS = Path("tests/evals/orchestrator-scenarios.json")

ORCHESTRATOR_PATHS = (
    Path("templates/agents/orchestrator.shared.md"),
    Path("src/claude/agents/orchestrator.md"),
    Path(".claude/agents/orchestrator.md"),
    Path(".github/agents/orchestrator.agent.md"),
    Path("src/copilot-cli/agents/orchestrator.agent.md"),
    Path("src/vs-code-agents/orchestrator.agent.md"),
)

STATE_RECORD = (
    "work-order fields, phase, exact next action, decisions with provenance "
    "(superseded ones marked), changed artifacts, validation run, blockers, "
    "repo, branch, worktree, head SHA, timestamp"
)

RULES = (
    "Label retrieved memory fact, decision, hypothesis, or stale",
    "A completion summary is not completion evidence.",
    "Compare recorded branch, worktree, head SHA, and artifacts with the live repository",
    "Reverted or superseded: HOLD",
    "only by commits that complete the next action is not a mismatch",
    "continue from the next step",
    "Restore ACCEPTANCE and RISK TIER",
    "HOLD and surface it",
    "Never mutate on a guess",
    "fails closed above read-only tier",
)


def _section(path: Path) -> str:
    text = (REPO_ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.count(HEADING) == 1, f"{path} must carry {HEADING!r} once"
    rest = text[text.find(HEADING) + len(HEADING) :]
    boundary = re.search(r"(?m)^## ", rest)
    return rest if boundary is None else rest[: boundary.start()]


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_state_record_lists_every_required_field(path: Path) -> None:
    section = _section(path)

    assert STATE_RECORD in " ".join(section.split()), f"{path} state record drifted"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_resume_check_states_the_fail_closed_rules(path: Path) -> None:
    section = _section(path)

    for rule in RULES:
        assert rule in section, f"{path} Resume Check is missing {rule!r}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_resume_check_precedes_the_output_bounds_section(path: Path) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    start = text.index("## Context Maintenance")
    assert start < text.index(HEADING) < text.index("## Output Bounds")


def _scenario(scenario_id: str) -> dict:
    payload = json.loads((REPO_ROOT / SCENARIOS).read_text(encoding="utf-8"))
    matches = [s for s in payload["scenarios"] if s["id"] == scenario_id]
    assert len(matches) == 1, f"{SCENARIOS} must carry exactly one {scenario_id}"
    return matches[0]


@pytest.mark.parametrize("scenario_id", ["S17", "S18", "S19", "S25", "S26"])
@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_graded_scenarios_stay_tied_to_the_resume_text(path: Path, scenario_id: str) -> None:
    scenario = _scenario(scenario_id)

    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert scenario["expected_reason_contains"] in _section(path)


def test_stale_handoff_scenario_models_a_wrong_branch_and_head() -> None:
    scenario = _scenario("S17")
    text = scenario["input"]

    assert scenario["expected_verdict"] == "BLOCK"
    assert "does not exist locally" in text
    assert "branch main at head 9a3e7f1" in text


@pytest.mark.parametrize("scenario_id", ["S25", "S26"])
def test_missing_field_and_reverted_scenarios_hold(scenario_id: str) -> None:
    assert _scenario(scenario_id)["expected_verdict"] == "BLOCK"


def test_matching_record_scenario_carries_every_state_field() -> None:
    text = _scenario("S18")["input"]

    for field in (
        "worktree",
        "timestamp",
        "phase",
        "risk tier",
        "acceptance",
        "provenance",
        "changed artifacts",
        "validation run",
        "blockers",
        "next action",
    ):
        assert field in text, field


def test_matching_and_already_done_scenarios_continue() -> None:
    assert _scenario("S18")["expected_verdict"] == "CONTINUE"
    assert _scenario("S19")["expected_verdict"] == "CONTINUE"
    assert "one commit ahead" in _scenario("S19")["input"]
