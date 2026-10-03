"""Static contract tests for the orchestrator work-order Handoff Contract.

The Handoff Contract in the orchestrator prompt is the single owner of the
work-order fields. These tests grade the shipped files: every orchestrator
surface carries the fields and the acceptance-evidence rule, and the
implementer, critic, and qa prompts point at the contract instead of copying it.

Behavioral claims (a plausible but wrong implementation that passes its own
check must be blocked, and a work order without acceptance or risk tier must not
be routed) are graded by the eval harness through scenarios ``S15`` and ``S16``
in ``tests/evals/orchestrator-scenarios.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HEADING = "## Handoff Contract"
SCENARIOS = Path("tests/evals/orchestrator-scenarios.json")

ORCHESTRATOR_PATHS = (
    Path("templates/agents/orchestrator.shared.md"),
    Path("src/claude/agents/orchestrator.md"),
    Path(".claude/agents/orchestrator.md"),
    Path(".github/agents/orchestrator.agent.md"),
    Path("src/copilot-cli/agents/orchestrator.agent.md"),
    Path("src/vs-code-agents/orchestrator.agent.md"),
)

REFERENCING_PATHS = (
    Path("templates/agents/implementer.shared.md"),
    Path("templates/agents/qa.shared.md"),
    Path("templates/agents/critic.shared.md"),
    Path(".claude/agents/implementer.md"),
    Path(".claude/agents/qa.md"),
    Path(".claude/agents/critic.md"),
)

FIELDS = (
    "OBJECTIVE:",
    "NON-GOALS:",
    "RISK TIER:",
    "ACCEPTANCE:",
    "STOP CONDITIONS:",
    "ESCALATE TO:",
    "ROLLBACK:",
)

RULES = (
    "single work-order contract",
    "is not routed",
    "not acceptance evidence",
    "cannot reach a successful terminal verdict",
    "completion record",
)


def _contract(path: Path) -> str:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    start = text.find(HEADING)
    assert start != -1, f"{path} is missing {HEADING!r}"
    rest = text[start + len(HEADING) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_contract_carries_every_work_order_field(path: Path) -> None:
    section = _contract(path)

    for field in FIELDS:
        assert field in section, f"{path} Handoff Contract is missing {field!r}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_contract_states_the_acceptance_rules(path: Path) -> None:
    section = _contract(path)

    for rule in RULES:
        assert rule in section, f"{path} Handoff Contract is missing {rule!r}"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_contract_names_the_unacceptable_evidence(path: Path) -> None:
    section = _contract(path)

    for weak in ("Benchmark capability", "token volume", "generated files", "completion claim"):
        assert weak in section, f"{path} does not name {weak!r} as non-evidence"


@pytest.mark.parametrize("path", REFERENCING_PATHS, ids=str)
def test_other_agents_reference_the_contract_without_copying_it(path: Path) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    assert "orchestrator Handoff Contract" in text
    for field in ("RISK TIER:", "STOP CONDITIONS:", "ROLLBACK:"):
        assert field not in text, f"{path} copies {field!r} instead of linking"


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_bare_findings_synthesis_is_invalid(path: Path) -> None:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")

    assert '"Based on findings, fix it" is invalid' in text
    for disposition in ("`CONTINUE`", "`RESTART`", "`BLOCK`", "`STOP`"):
        assert disposition in text


def _scenario(scenario_id: str) -> dict:
    payload = json.loads((REPO_ROOT / SCENARIOS).read_text(encoding="utf-8"))
    matches = [s for s in payload["scenarios"] if s["id"] == scenario_id]
    assert len(matches) == 1, f"{SCENARIOS} must carry exactly one {scenario_id}"
    return matches[0]


def _synthesis(path: Path) -> str:
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    start = text.find("## Synthesis Protocol")
    assert start != -1, f"{path} is missing the Synthesis Protocol"
    return text[start : text.find("\n## ", start + 1)]


SCENARIO_EXPECTATIONS = {
    "S15": ("BLOCK", "contract"),
    "S16": ("BLOCK", "contract"),
    "S21": ("BLOCK", "synthesis"),
    "S22": ("ROUTE", "contract"),
    "S23": ("BLOCK", "contract"),
    "S24": ("BLOCK", "contract"),
}


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_conflicting_findings_scenario_grades_the_disposition(path: Path) -> None:
    scenario = _scenario("S20")

    assert scenario["expected_verdict"] == "CONTINUE"
    assert scenario["verdict_options"] == ["CONTINUE", "RESTART", "BLOCK", "STOP"]
    for disposition in scenario["verdict_options"]:
        assert f"`{disposition}`" in _synthesis(path)


@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_risk_tier_reuses_the_adr_112_labels(path: Path) -> None:
    section = _contract(path)

    assert (
        "ADR-112 tier: read-only | reversible-local | shared-repository | consequential" in section
    )


@pytest.mark.parametrize("scenario_id", sorted(SCENARIO_EXPECTATIONS))
@pytest.mark.parametrize("path", ORCHESTRATOR_PATHS, ids=str)
def test_graded_scenarios_stay_tied_to_the_contract_text(path: Path, scenario_id: str) -> None:
    scenario = _scenario(scenario_id)
    verdict, section = SCENARIO_EXPECTATIONS[scenario_id]
    text = _contract(path) if section == "contract" else _synthesis(path)

    assert scenario["expected_verdict"] == verdict
    assert verdict in scenario["verdict_options"]
    keyword = scenario.get("expected_reason_contains")
    assert keyword is None or keyword.lower() in text.lower()


def test_weak_self_check_scenario_models_the_wrong_but_plausible_implementation() -> None:
    text = _scenario("S15")["input"].lower()

    assert "reports done" in text
    assert "passing test it wrote" in text
    assert "independently" in text
