"""Contract tests for the two canonical amendments made for issue #5410.

Issue #5410 reconciles the standalone `you` profile into existing canonical
owners. Two behaviors had no effective owner and were added to the narrowest
one:

1. Recurring defect: a defect class that returns gets a deterministic guard,
   not another one-off patch. Owner: SHOULD 18 of the testing rule.
2. Grading eval results: an underpowered comparison is inconclusive, not a
   preference. Owner: the ai-agents-research-methodology skill.

These tests prove four things offline:

1. Every rendered surface carries each clause.
2. A mutation check removes one clause at a time and proves the checker
   notices, so the clauses are not decoration.
3. The runtime fixture corpus loads and its controls discriminate for the
   documented reason.
4. The recurring-defect clause stays scoped: it names the first-occurrence
   limit that stops it from demanding a framework for a one-off defect.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import runtime_parity

REPO_ROOT = Path(__file__).resolve().parents[1]

TESTING_SURFACES = (
    Path("templates/rules/testing.md"),
    Path(".claude/rules/testing.md"),
    Path("src/claude/rules/testing.md"),
    Path(".github/instructions/testing.instructions.md"),
    Path("src/copilot-cli/instructions/testing.instructions.md"),
    Path("tests/build_scripts/fixtures/rule_templates_b2/expected/testing.md"),
    Path("src/cursor/rules/testing.mdc"),
)

METHODOLOGY_SURFACES = (
    Path("templates/skills/ai-agents-research-methodology.SKILL.md.tmpl"),
    Path(".claude/skills/ai-agents-research-methodology/SKILL.md"),
)

RECURRENCE_CLAUSES: dict[str, str] = {
    "returning-class-gets-a-guard": (
        "**A defect class that returns gets a guard, not another patch.**"
    ),
    "find-why-earlier-fix-failed": "find why the earlier fix did not hold",
    "deterministic-check-on-recurrence": (
        "add a deterministic check that fails on recurrence (a test, validator, or type)"
    ),
    "warning-is-not-a-guard": "A warning or doc note is not a guard.",
    "first-occurrence-limit": (
        "A first occurrence takes the targeted fix and its regression test, nothing broader."
    ),
}

GRADING_CLAUSES: dict[str, str] = {
    "inconclusive-not-preference": "is inconclusive, not a preference",
    "report-sample-and-interval": "Report the sample size and an interval or margin",
    "direction-alone-does-not-promote": (
        "A directional delta alone does not promote an ADR or justify a model pin"
    ),
    "rerun-to-confirm": "rerun it to confirm",
    "adr-111-bar": "ADR-111 rule 2",
}

FIXTURES_PATH = REPO_ROOT / "tests" / "evals" / "structural-recurrence-runtime-fixtures.json"

EXPECTED_FIXTURE_IDS = {
    "recurring-defect-adds-guard",
    "recurring-defect-explanation-is-not-a-guard",
    "first-occurrence-targeted-fix-only",
}


def _flat(path: Path) -> str:
    return " ".join((REPO_ROOT / path).read_text(encoding="utf-8").split())


def missing(text: str, clauses: dict[str, str]) -> list[str]:
    """Return ids of clauses absent from ``text`` after whitespace folding."""
    flat = " ".join(text.split())
    return [key for key, clause in clauses.items() if " ".join(clause.split()) not in flat]


@pytest.mark.parametrize("path", TESTING_SURFACES, ids=str)
def test_testing_surface_carries_every_recurrence_clause(path: Path) -> None:
    assert missing(_flat(path), RECURRENCE_CLAUSES) == []


@pytest.mark.parametrize("path", METHODOLOGY_SURFACES, ids=str)
def test_methodology_surface_carries_every_grading_clause(path: Path) -> None:
    assert missing(_flat(path), GRADING_CLAUSES) == []


@pytest.mark.parametrize("clause_id", sorted(RECURRENCE_CLAUSES))
def test_removing_a_recurrence_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = _flat(TESTING_SURFACES[0])
    mutated = source.replace(" ".join(RECURRENCE_CLAUSES[clause_id].split()), "")
    assert missing(mutated, RECURRENCE_CLAUSES) == [clause_id]


@pytest.mark.parametrize("clause_id", sorted(GRADING_CLAUSES))
def test_removing_a_grading_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = _flat(METHODOLOGY_SURFACES[0])
    mutated = source.replace(" ".join(GRADING_CLAUSES[clause_id].split()), "")
    assert missing(mutated, GRADING_CLAUSES) == [clause_id]


def test_checker_reports_every_clause_for_unrelated_text() -> None:
    assert sorted(missing("nothing relevant here", RECURRENCE_CLAUSES)) == sorted(
        RECURRENCE_CLAUSES
    )
    assert sorted(missing("", GRADING_CLAUSES)) == sorted(GRADING_CLAUSES)


def test_recurrence_clause_appears_once_per_testing_surface() -> None:
    """No duplicated normative block: the clause is authored once per surface."""
    for path in TESTING_SURFACES:
        assert (
            _flat(path).count("**A defect class that returns gets a guard, not another patch.**")
            == 1
        ), path


def test_fixture_corpus_loads_with_the_required_scenarios() -> None:
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)
    assert {f.fixture_id for f in fixtures} == EXPECTED_FIXTURE_IDS


def test_every_fixture_carries_a_semantic_assertion() -> None:
    for fixture in runtime_parity.load_fixtures(FIXTURES_PATH):
        assert "semantic" in {spec.kind for spec in fixture.assertions}, fixture.fixture_id


def test_scope_note_denies_the_regex_backstop_semantic_authority() -> None:
    note = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"].lower()
    assert "not the semantic authority" in note


def test_patch_only_negative_control_names_no_guard() -> None:
    """Negative control 1: a patch-only reply to a recurring defect has no guard."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "recurring-defect-adds-guard"
    ]
    guard = re.compile(r"(?i)(test|validator|lint|type)[\s\S]{0,160}\bfails?\b")
    assert guard.search(fixture.positive.response)
    assert not guard.search(fixture.negative.response)


def _overbuilt_pattern() -> re.Pattern[str]:
    """The first-occurrence fixture's not_regex, read from the corpus itself."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "first-occurrence-targeted-fix-only"
    ]
    patterns = [spec.pattern for spec in fixture.assertions if spec.kind == "not_regex"]
    assert len(patterns) == 1
    return re.compile(patterns[0])


def test_overbuilt_negative_control_builds_enforcement_for_a_first_occurrence() -> None:
    """Negative control 2: the clause must not license a framework for a one-off."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "first-occurrence-targeted-fix-only"
    ]
    overbuilt = _overbuilt_pattern()
    assert overbuilt.search(fixture.negative.response)
    assert not overbuilt.search(fixture.positive.response)


def test_the_two_fixtures_give_opposite_prompts_about_history() -> None:
    """The pair only discriminates if one prompt has prior fixes and the other has none."""
    fixtures = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}
    assert "already patched" in fixtures["recurring-defect-adds-guard"].prompt
    assert "no earlier fix" in fixtures["first-occurrence-targeted-fix-only"].prompt


def test_regression_test_described_as_a_guard_is_not_overbuilt() -> None:
    """A regression test is allowed on a first occurrence, even when called a guard."""
    overbuilt = _overbuilt_pattern()
    for reply in (
        "I added a regression test as a guard for this input.",
        "I added a regression test for that input.",
        "I wrote a guard clause test for the trailing Z case.",
    ):
        assert not overbuilt.search(reply), reply


@pytest.mark.parametrize(
    "reply",
    [
        "I added a repo-wide guard for every parser.",
        "I built a class-wide guard around int() parsing.",
        "I introduced a validator for all timestamps.",
    ],
)
def test_class_wide_enforcement_on_a_first_occurrence_is_overbuilt(reply: str) -> None:
    assert _overbuilt_pattern().search(reply), reply


def test_explain_only_negative_control_adds_no_check() -> None:
    """Negative control 3: explaining why earlier fixes failed is not a guard."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "recurring-defect-explanation-is-not-a-guard"
    ]
    guard = re.compile(r"(?i)(test|validator|lint|type)[\s\S]{0,160}\bfails?\b")
    assert "keeps coming back because" in fixture.negative.response
    assert guard.search(fixture.positive.response)
    assert not guard.search(fixture.negative.response)


def test_semantic_rubric_requires_the_check_and_rejects_explain_only() -> None:
    """The semantic authority must not let an explanation stand in for the guard."""
    fixtures = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}
    rubric = next(
        spec.rubric
        for spec in fixtures["recurring-defect-adds-guard"].assertions
        if spec.kind == "semantic"
    )
    assert "or explains why" not in rubric
    assert "only explains why the earlier fixes did not hold" in rubric
