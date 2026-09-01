"""Registration tests for the critic/qa finding-quota reconciliation (issue #5404).

The runtime grading of these review verdicts happens against a model via
``scripts/eval/eval-prompt-change.py`` and cannot run here. These tests assert
the *static* contract that the reconciliation depends on:

1. the clean-review zero-finding scenario is registered as an APPROVE case, so
   the eval harness has evidence that a critic may pass without manufacturing a
   finding;
2. no critic or qa surface still carries the ``Find at least three issues``
   minimum-finding quota, and every surface states there is no minimum count;
3. the pre-existing planted-defect scenarios still expect ``CHALLENGE`` so the
   clean case did not weaken the reviewer-asymmetry experiment.

Positive, negative, and edge cases per ``.agents/governance/TESTING-RIGOR.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

CRITIC_SCENARIOS_PATH = Path("tests/evals/critic-scenarios.json")
CLEAN_REVIEW_SCENARIO_ID = "CLEAN-1"

# The planted-defect fixtures the clean case must not displace. Each expects a
# CHALLENGE verdict; they are the reviewer-asymmetry experiment.
PLANTED_DEFECT_SCENARIO_IDS = ("S1", "S2", "S3", "S4", "S5", "CMO-1", "CMO-2")

OLD_QUOTA_PHRASE = "Find at least three issues"
NO_QUOTA_PHRASE = "no minimum finding count"

CRITIC_SURFACES = (
    Path("templates/agents/critic.shared.md"),
    Path(".claude/agents/critic.md"),
    Path(".github/agents/critic.agent.md"),
    Path("src/claude/critic.md"),
    Path("src/copilot-cli/agents/critic.agent.md"),
    Path("src/vs-code-agents/critic.agent.md"),
)

QA_SURFACES = (
    Path("templates/agents/qa.shared.md"),
    Path(".claude/agents/qa.md"),
    Path(".github/agents/qa.agent.md"),
    Path("src/claude/qa.md"),
    Path("src/copilot-cli/agents/qa.agent.md"),
    Path("src/vs-code-agents/qa.agent.md"),
)

ALL_SURFACES = CRITIC_SURFACES + QA_SURFACES


def _load_critic_scenarios() -> list[dict]:
    payload = json.loads((REPO_ROOT / CRITIC_SCENARIOS_PATH).read_text(encoding="utf-8"))
    return payload["scenarios"]


def test_clean_review_scenario_registered_as_approve() -> None:
    """Positive: the zero-finding clean review exists exactly once and approves."""
    matches = [s for s in _load_critic_scenarios() if s["id"] == CLEAN_REVIEW_SCENARIO_ID]
    assert len(matches) == 1, (
        f"{CRITIC_SCENARIOS_PATH} must carry exactly one scenario "
        f"{CLEAN_REVIEW_SCENARIO_ID!r}; found {len(matches)}. It is the graded "
        "evidence that a critic may pass with zero findings."
    )
    scenario = matches[0]
    assert scenario["expected_verdict"] == "APPROVE"
    assert scenario["expected_verdict"] in scenario["verdict_options"]
    assert "CHALLENGE" in scenario["verdict_options"], (
        "APPROVE must be the graded choice against a real CHALLENGE alternative, "
        "not the only option."
    )
    assert scenario["expected_reason_contains"] == "auth.ts:47", (
        "The clean-review verdict must turn on the critic citing a concrete "
        "file-and-line anchor, not a generic 'examined' claim a vacuous reason "
        "could also satisfy."
    )


@pytest.mark.parametrize("surface", ALL_SURFACES, ids=lambda p: str(p))
def test_surface_has_no_minimum_finding_quota(surface: Path) -> None:
    """Negative: no critic/qa surface keeps the minimum-finding quota."""
    text = (REPO_ROOT / surface).read_text(encoding="utf-8")
    assert OLD_QUOTA_PHRASE not in text, (
        f"{surface} still carries the manufactured-work quota {OLD_QUOTA_PHRASE!r}."
    )
    assert NO_QUOTA_PHRASE in text, (
        f"{surface} must state {NO_QUOTA_PHRASE!r} so zero findings is a valid pass."
    )


def test_planted_defect_scenarios_preserved() -> None:
    """Edge: the clean case did not weaken the planted-defect experiment."""
    by_id = {s["id"]: s for s in _load_critic_scenarios()}
    for scenario_id in PLANTED_DEFECT_SCENARIO_IDS:
        assert scenario_id in by_id, (
            f"planted-defect scenario {scenario_id!r} was removed; the reviewer-"
            "asymmetry experiment must survive the clean-review addition."
        )
        assert by_id[scenario_id]["expected_verdict"] == "CHALLENGE", (
            f"planted-defect scenario {scenario_id!r} must still expect CHALLENGE."
        )
