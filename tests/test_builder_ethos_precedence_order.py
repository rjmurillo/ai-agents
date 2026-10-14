"""Cross-surface precedence-order tests for builder-ethos.md (issue #5535).

``builder-ethos.md`` is always-on. It must rank mandatory safety and
repository policy above the current user request, and every surface that
states the order must state it identically, so a mirror cannot drift from the
canonical template again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL = Path("templates/rules/builder-ethos.md")

RULE_SURFACES = (
    CANONICAL,
    Path(".claude/rules/builder-ethos.md"),
    Path("src/claude/rules/builder-ethos.md"),
    Path(".github/instructions/builder-ethos.instructions.md"),
    Path("src/copilot-cli/instructions/builder-ethos.instructions.md"),
    Path("tests/build_scripts/fixtures/rule_templates_b2/expected/builder-ethos.md"),
)

SKILL_SURFACES = (
    Path(".claude/skills/avoiding-manufactured-work/SKILL.md"),
    Path("src/claude/skills/avoiding-manufactured-work/SKILL.md"),
    Path("src/codex/skills/avoiding-manufactured-work/SKILL.md"),
    Path("src/copilot-cli/skills/avoiding-manufactured-work/SKILL.md"),
)

ADR_PATH = Path(".project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md")

EXPECTED_ORDER = (
    "`system/host requirements > mandatory safety/repository policy > "
    "current user request > frozen task contract > optional improvements`."
)
REJECTED_ORDER = (
    "`system/host requirements > current user request > "
    "mandatory safety/repository policy > frozen task contract > optional improvements`."
)
CARVE_OUT = "but never mandatory policy (section 4)"

POLICY_DEFINITION = (
    "Mandatory policy: the MUST and MUST NOT items in `universal.md` and "
    "`security.md`, and the `AGENTS.md` Never list."
)

CHAIN_PATTERN = re.compile(r"^`system/host requirements > .*`\.$", re.MULTILINE)


def _text(path: Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _chains(path: Path) -> list[str]:
    return CHAIN_PATTERN.findall(_text(path))


@pytest.mark.parametrize("path", RULE_SURFACES, ids=str)
def test_surface_states_the_policy_first_order_exactly_once(path: Path) -> None:
    assert _chains(path) == [EXPECTED_ORDER]


@pytest.mark.parametrize("path", (*RULE_SURFACES, ADR_PATH), ids=str)
def test_rejected_user_first_order_is_absent(path: Path) -> None:
    normalized = " ".join(_text(path).split())
    assert REJECTED_ORDER not in normalized


@pytest.mark.parametrize("path", RULE_SURFACES, ids=str)
def test_mandatory_policy_is_defined_by_named_sources(path: Path) -> None:
    text = _text(path)
    assert POLICY_DEFINITION in text
    assert "No request lowers them." in text


@pytest.mark.parametrize("path", RULE_SURFACES, ids=str)
def test_policy_ranks_above_request_by_position(path: Path) -> None:
    (chain,) = _chains(path)
    assert chain.index("mandatory safety/repository policy") < chain.index("current user request")


@pytest.mark.parametrize("path", RULE_SURFACES, ids=str)
def test_user_sovereignty_carries_the_policy_carve_out_twice(path: Path) -> None:
    text = _text(path)
    assert text.count(CARVE_OUT) == 2, (
        "Precedence Stack item 1 and section 3 must both carry the carve-out"
    )


@pytest.mark.parametrize("path", RULE_SURFACES, ids=str)
def test_section_3_no_longer_overrides_all_others(path: Path) -> None:
    assert "the one rule that overrides all others" not in _text(path)


@pytest.mark.parametrize("path", SKILL_SURFACES, ids=str)
def test_skill_carries_no_ordering_of_its_own(path: Path) -> None:
    text = _text(path)
    assert not CHAIN_PATTERN.search(text)
    assert REJECTED_ORDER not in " ".join(text.split())
    assert "system / host requirements" not in text


def test_every_surface_states_the_same_order_as_the_canonical_template() -> None:
    canonical = _chains(CANONICAL)
    assert canonical, "canonical template lost its precedence line"
    for path in RULE_SURFACES:
        assert _chains(path) == canonical, f"{path} drifted from {CANONICAL}"


def test_adr_105_records_the_same_order_as_the_rule() -> None:
    text = _text(ADR_PATH)
    assert EXPECTED_ORDER in text
    assert "deviates from #5404's literal precedence text" in " ".join(text.split())
