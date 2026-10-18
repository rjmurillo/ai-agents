"""Pin the system-capability doctrine to one canonical home (issue #6656).

The objective (optimize verified system outcomes, not unaided model
competence) lives only in ``.agents/governance/agent-design-principles.md``.
``AGENTS.md`` carries a one-clause pointer so an agent with no prior context
can find it. These tests fail if the pointer drifts from the doc, if the doc
loses the four-part distinction, or if the doctrine is copied into an
always-on rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / ".agents" / "governance" / "agent-design-principles.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
HEADING = "## Operating Objective: System Capability, Not Model Competence"
FOUR_PARTS = ("Base model", "Agent system", "External state", "Measurable outcomes")
ALWAYS_ON_RULES = (
    REPO_ROOT / "templates" / "rules" / "universal.md",
    REPO_ROOT / "templates" / "rules" / "builder-ethos.md",
    REPO_ROOT / "templates" / "rules" / "voice.md",
)


def test_doc_has_heading_exactly_once() -> None:
    assert DOC.read_text(encoding="utf-8").count(HEADING) == 1


@pytest.mark.parametrize("part", FOUR_PARTS)
def test_doc_names_each_system_part(part: str) -> None:
    assert part in DOC.read_text(encoding="utf-8")


def test_doc_does_not_claim_frozen_weights_mean_no_system_learning() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "Frozen weights do not stop the agent system" in text


def test_doc_links_outcome_measurement_issue_instead_of_reimplementing() -> None:
    assert "#5768" in DOC.read_text(encoding="utf-8")


def test_agents_md_points_at_the_doc_stem() -> None:
    stem = DOC.stem
    assert stem in AGENTS_MD.read_text(encoding="utf-8")
    assert DOC.is_file()


def test_agents_md_pointer_states_the_objective() -> None:
    text = AGENTS_MD.read_text(encoding="utf-8")
    assert "model competence" in text


@pytest.mark.parametrize("rule", ALWAYS_ON_RULES, ids=lambda p: p.name)
def test_doctrine_is_not_copied_into_always_on_rules(rule: Path) -> None:
    assert HEADING not in rule.read_text(encoding="utf-8")
