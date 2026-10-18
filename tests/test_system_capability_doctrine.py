"""Pin the system-capability doctrine to one canonical home (issue #6656).

The objective (optimize verified system outcomes, not unaided model
competence) lives only in ``.agents/governance/agent-design-principles.md``.
``AGENTS.md`` and its routing detail mirror carry a one-clause pointer so an
agent with no prior context can find it. These tests fail if the pointer
drifts from the doc, if the doc loses the four-part distinction, or if the
doctrine is copied into an always-on rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / ".agents" / "governance" / "agent-design-principles.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
HEADING = "## Operating Objective: System Capability, Not Model Competence"
FOUR_PARTS = ("Base model", "Agent system", "External state", "Measurable outcomes")
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
ROUTING_DETAIL = REPO_ROOT / ".project-toolkit" / "context" / "AGENTS-details" / "routing.md"
POINTER_FILES = (AGENTS_MD, ROUTING_DETAIL)
DOCTRINE_SENTENCES = (
    "Frozen weights do not stop the agent system",
    "Optimize verified task outcomes of the whole system",
)
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


def _context_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("Context|")
    ]


@pytest.mark.parametrize("guide", POINTER_FILES, ids=lambda p: p.name)
def test_context_line_carries_one_clause_pointer(guide: Path) -> None:
    lines = _context_lines(guide)
    assert len(lines) == 1, f"{guide} needs exactly one Context| line, got {len(lines)}"
    line = lines[0]
    assert DOC.stem in line
    assert "model competence" in line
    assert DOC.is_file()


def _pointer_in_one_clause(line: str) -> bool:
    clauses = [c for c in line.split("|") if DOC.stem in c]
    return len(clauses) == 1 and "model competence" in clauses[0]


@pytest.mark.parametrize("guide", POINTER_FILES, ids=lambda p: p.name)
def test_pointer_names_doc_and_objective_in_same_clause(guide: Path) -> None:
    (line,) = _context_lines(guide)
    assert _pointer_in_one_clause(line)


def test_pointer_check_rejects_a_split_pointer() -> None:
    split = "Context|goal: not model competence|x|gov `agent-design-principles`"
    assert not _pointer_in_one_clause(split)


def test_pointer_check_rejects_a_missing_pointer() -> None:
    assert not _pointer_in_one_clause("Context|script/rule before model")


def test_claude_md_keeps_orchestrator_default_for_non_trivial_work() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert 'Task(subagent_type="orchestrator")` by default for non-trivial work' in text


@pytest.mark.parametrize("rule", ALWAYS_ON_RULES, ids=lambda p: p.name)
def test_doctrine_is_not_copied_into_always_on_rules(rule: Path) -> None:
    text = rule.read_text(encoding="utf-8")
    assert HEADING not in text
    for sentence in DOCTRINE_SENTENCES:
        assert sentence not in text
