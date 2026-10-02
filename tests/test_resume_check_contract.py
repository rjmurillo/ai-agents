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
    "(superseded marked), changed artifacts, validation run, blockers, residual risks, "
    "remote owner/name, branch, worktree, head SHA, timestamp"
)

RULES = (
    "Label retrieved memory fact, decision, or hypothesis, and verified, unverified, or stale",
    "HOLD on unverified load-bearing context",
    "A completion summary is not completion evidence.",
    "Compare recorded remote owner/name, branch, worktree, head SHA, and artifacts with the live repository",
    "Reverted or superseded: HOLD",
    "A live change caused solely by the next action is not a mismatch",
    "continue from the next step",
    "Restore ACCEPTANCE and RISK TIER",
    "HOLD and surface it",
    "Never mutate on a guess",
    "Delegate returns follow the Handoff Contract completion record.",
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


@pytest.mark.parametrize("scenario_id", ["S17", "S18", "S19", "S25", "S26", "S29", "S30"])
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


COMPLETE_RECORD_TERMS = (
    "objective",
    "non-goals",
    "shared-repository",
    "acceptance",
    "stop conditions",
    "escalation owner",
    "rollback",
    "phase",
    "next action",
    "decisions",
    "provenance",
    "changed artifacts",
    "validation run",
    "blockers",
    "residual risks",
    "rjmurillo/ai-agents",
    "branch",
    "worktree",
    "head ",
    "timestamp",
)


@pytest.mark.parametrize("scenario_id", ["S18", "S19"])
def test_continue_scenarios_carry_a_complete_valid_record(scenario_id: str) -> None:
    text = _scenario(scenario_id)["input"]

    for term in COMPLETE_RECORD_TERMS:
        assert term in text, f"{scenario_id} record is missing {term!r}"
    assert "shared-repo," not in text


def _handoff_contract(path: Path) -> str:
    text = (REPO_ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("## Handoff Contract")
    boundary = re.search(r"(?m)^## ", text[start + 3 :])
    assert boundary is not None, f"{path} has no section after the Handoff Contract"
    return text[start : start + 3 + boundary.start()]


@pytest.mark.parametrize("scenario_id", ["S27", "S28"])
@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_delegate_return_scenarios_tie_to_the_handoff_contract(
    path: Path, scenario_id: str
) -> None:
    scenario = _scenario(scenario_id)

    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert scenario["expected_reason_contains"] in _handoff_contract(path)


def test_delegate_return_scenarios_grade_the_tier_boundary() -> None:
    assert _scenario("S27")["expected_verdict"] == "REJECT"
    assert "shared-repository" in _scenario("S27")["input"]
    assert _scenario("S28")["expected_verdict"] == "ACCEPT"
    assert "read-only" in _scenario("S28")["input"]


def test_matching_and_already_done_scenarios_continue() -> None:
    assert _scenario("S18")["expected_verdict"] == "CONTINUE"
    assert _scenario("S19")["expected_verdict"] == "CONTINUE"
    assert "one commit ahead" in _scenario("S19")["input"]
