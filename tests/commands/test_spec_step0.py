"""Tests for Step 0 First Principles Gate in /spec command.

Refs #1926, REQ-006, DESIGN-006, TASK-006, PLAN-1926.

Verifies the static structure and parser-checkable behavior of Step 0
instructions in `.claude/commands/spec.md` and its Copilot CLI mirror at
`src/copilot-cli/skills/spec/SKILL.md`. The parser logic lives in
`tests/commands/_step0_parser.py`; this file holds only test cases.

Six dynamic LLM-dependent cases (T2, T3, T4, T10, T12, T13) are documented
manual spot-checks per PLAN-1926; they probe model interpretation of the
spec, not the spec text itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.commands.step0_parser import (
    baseline_answers,
    evaluate_step0,
    extract_step0_block,
    extract_step1_paragraph,
    extract_step9_block,
    extract_tier5_bullet,
    hedge_match,
    parse_hedge_phrases,
    q1_aspirational,
    q3_specific,
    q5_speculative,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_MD = PROJECT_ROOT / ".claude" / "commands" / "spec.md"
SKILL_MD = PROJECT_ROOT / "src" / "copilot-cli" / "skills" / "spec" / "SKILL.md"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def hedge_phrases(spec_text: str) -> list[str]:
    return parse_hedge_phrases(spec_text)


# ---------------------------------------------------------------------------
# Static-1: structural tokens present in spec.md
# ---------------------------------------------------------------------------


def test_step0_heading_precedes_step1_in_spec_md(spec_text: str) -> None:
    """AC-1a: the Step 0 heading appears before Step 1 in the file."""
    step0_offset = spec_text.find("### Step 0:")
    step1_offset = spec_text.find("\n1. Clarify the problem")
    assert step0_offset != -1, "missing '### Step 0:' heading"
    assert step1_offset != -1, "missing Step 1 list item"
    assert step0_offset < step1_offset, "Step 0 must appear before Step 1"


def test_step1_references_step0_block(spec_text: str) -> None:
    """AC-7a, AC-7b: Step 1 prose references the Step 0 block and forbids re-elicitation."""
    step1_text = extract_step1_paragraph(spec_text)
    assert "Step 0" in step1_text
    assert "Q1-Q6" in step1_text
    assert "Do not re-elicit" in step1_text


def test_tier5_replaces_why_not_simpler(spec_text: str) -> None:
    """AC-8: Tier 5 bullet replaces the standalone 'why not simpler?' challenge.

    The bullet may mention "why not simpler?" as a meta-reference to the v1
    text being replaced; the structural check is that the active directive
    is the Q4 re-validation, not the v1 standalone challenge directive.
    """
    tier5_text = extract_tier5_bullet(spec_text)
    assert "Re-validate Step 0 Q4" in tier5_text
    assert "Explicit why not simpler?" not in tier5_text


def test_step9_contains_binary_checks(spec_text: str) -> None:
    """AC-9: Step 9 critic pre-mortem contains Check 9a/9b/9c with PASS/FAIL phrasing."""
    assert "Check 9a" in spec_text
    assert "Check 9b" in spec_text
    assert "Check 9c" in spec_text
    assert "PASS:" in spec_text
    assert "FAIL" in spec_text
    assert "SHALL NOT return APPROVED" in spec_text


def test_step0_kill_criteria_reference(spec_text: str) -> None:
    """AC-13: Step 0 references kill criteria + tally infrastructure."""
    assert "STEP-0-METRICS.md" in spec_text
    assert "kill criteria" in spec_text.lower()


def test_auto_mode_halt_token_in_spec_md(spec_text: str) -> None:
    """AC-12 (static): the auto-mode halt reason appears verbatim."""
    assert "STEP_0_REQUIRES_ELICITATION" in spec_text


def test_auto_mode_halt_token_in_skill_md(skill_text: str) -> None:
    """AC-12 (static): SKILL.md mirrors the auto-mode halt reason."""
    assert "STEP_0_REQUIRES_ELICITATION" in skill_text


# ---------------------------------------------------------------------------
# Static-2: edited sections byte-identical between spec.md and SKILL.md
# ---------------------------------------------------------------------------


def test_step0_block_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Step 0 block byte-identical between spec.md and SKILL.md."""
    assert extract_step0_block(spec_text) == extract_step0_block(skill_text)


def test_step1_paragraph_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Step 1 narrowed paragraph identical."""
    assert extract_step1_paragraph(spec_text) == extract_step1_paragraph(skill_text)


def test_tier5_bullet_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Tier 5 bullet identical."""
    assert extract_tier5_bullet(spec_text) == extract_tier5_bullet(skill_text)


def test_step9_block_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Step 9 critic block identical."""
    assert extract_step9_block(spec_text) == extract_step9_block(skill_text)


# ---------------------------------------------------------------------------
# Hedge phrase list contract
# ---------------------------------------------------------------------------


def test_hedge_phrase_list_parsed(spec_text: str) -> None:
    """The parser finds at least 15 hedge phrases in spec.md."""
    phrases = parse_hedge_phrases(spec_text)
    assert len(phrases) >= 15
    for required in ["would be nice", "we believe", "stakeholders want", "probably"]:
        assert required in phrases


def test_no_standalone_should_might_could(spec_text: str) -> None:
    """REQ-006-02: standalone 'should'/'might'/'could' MUST NOT be hedge phrases."""
    phrases = parse_hedge_phrases(spec_text)
    for forbidden in ["should", "might", "could"]:
        assert forbidden not in phrases


# ---------------------------------------------------------------------------
# Parser-checkable scenarios T1, T3, T4, T5, T6, T7, T8, T11
# ---------------------------------------------------------------------------


def test_t1_hedge_phrase_in_q3_triggers_h1(hedge_phrases: list[str]) -> None:
    """T1: 'stakeholders want' in Q3 fires H1 halt."""
    answers = baseline_answers()
    answers["Q3"] = "stakeholders want a faster gate"
    assert evaluate_step0(answers, hedge_phrases) == "H1"


def test_t3_speculative_q5_triggers_h2(hedge_phrases: list[str]) -> None:
    """T3: Q5 with no quote, no citation, no named source fires H2."""
    answers = baseline_answers()
    answers["Q5"] = "users find this slow"
    assert evaluate_step0(answers, hedge_phrases) == "H2"


def test_t4_q5_with_citation_passes(hedge_phrases: list[str]) -> None:
    """T4 (parser side): Q5 with PR citation passes the speculative test."""
    answers = baseline_answers()
    answers["Q5"] = "PR 1887 retro line 305 names the framework gap as out of scope."
    assert evaluate_step0(answers, hedge_phrases) is None


def test_t5_aspirational_q1_triggers_h3(hedge_phrases: list[str]) -> None:
    """T5: aspirational Q1 fires H3 halt."""
    answers = baseline_answers()
    answers["Q1"] = "users in general would want this"
    assert evaluate_step0(answers, hedge_phrases) == "H3"


def test_t6_concrete_q1_passes(hedge_phrases: list[str]) -> None:
    """T6: Q1 with three named teams + ticket numbers passes."""
    answers = baseline_answers()
    assert evaluate_step0(answers, hedge_phrases) is None


def test_t7_generic_q3_triggers_h4(hedge_phrases: list[str]) -> None:
    """T7: generic Q3 ('engineers in general') fires H3 (aspirational) or H4 (specificity)."""
    answers = baseline_answers()
    answers["Q3"] = "engineers in general"
    trigger = evaluate_step0(answers, hedge_phrases)
    assert trigger in {"H3", "H4"}


def test_t8_specific_q3_passes(hedge_phrases: list[str]) -> None:
    """T8: Q3 with named individual + system + frequency passes."""
    answers = baseline_answers()
    assert evaluate_step0(answers, hedge_phrases) is None


def test_t11_partial_completion_triggers_h5(hedge_phrases: list[str]) -> None:
    """T11: empty Q4-Q6 fires H5 halt (partial completion)."""
    answers = baseline_answers()
    answers["Q4"] = ""
    answers["Q5"] = ""
    answers["Q6"] = ""
    assert evaluate_step0(answers, hedge_phrases) == "H5"


def test_rfc_2119_should_in_q5_does_not_trigger_h1(hedge_phrases: list[str]) -> None:
    """T2 (parser side): standalone 'should' in Q5 must not fire H1."""
    answers = baseline_answers()
    answers["Q5"] = (
        'Issue #1700 says "the system should retry transient KeyVault timeouts"; '
        "we observed 3 such timeouts last week."
    )
    assert evaluate_step0(answers, hedge_phrases) != "H1"


def test_quoted_hedge_in_q5_triggers_h1_parser_side(hedge_phrases: list[str]) -> None:
    """Documented limitation: parser cannot distinguish authored hedge from
    quoted-counter-example hedge. Spec REQ-006-02 says the boundary is
    instruction-level; this test pins parser behavior so a future fix that
    adds quote-aware exclusion is detectable."""
    answers = baseline_answers()
    answers["Q5"] = 'The old ticket said "would be nice"; we observed timeouts in #1700.'
    assert evaluate_step0(answers, hedge_phrases) == "H1"


# ---------------------------------------------------------------------------
# Direct unit tests for parser helpers (Gate 1 finding F1)
# ---------------------------------------------------------------------------


class TestHedgeMatch:
    """Direct unit tests for `hedge_match`."""

    def test_matches_canonical_phrase(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("we believe X", hedge_phrases) == "we believe"

    def test_case_insensitive(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("WE BELIEVE X", hedge_phrases) == "we believe"

    def test_eventually_consistent_is_technical_term(self, hedge_phrases: list[str]) -> None:
        """`eventually consistent` is a load-bearing technical term, not a hedge."""
        assert hedge_match("Storage is eventually consistent.", hedge_phrases) is None

    def test_eventually_alone_is_a_hedge(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("This will eventually work.", hedge_phrases) == "eventually"

    def test_no_match(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("Concrete observation with citation #1700.", hedge_phrases) is None

    def test_partial_word_no_match(self, hedge_phrases: list[str]) -> None:
        """`somedayer` (made-up word) must NOT match `someday` due to word boundary."""
        assert hedge_match("The somedayer pattern is here.", hedge_phrases) is None


class TestQ1Aspirational:
    """Direct unit tests for `q1_aspirational`."""

    def test_named_team_passes(self) -> None:
        assert not q1_aspirational("Bleu team escalated this in #1700.")

    def test_named_service_passes(self) -> None:
        assert not q1_aspirational("KeyVault service failed three times.")

    def test_ticket_only_passes(self) -> None:
        assert not q1_aspirational("Three teams reported issues in #1700, #1820, #1850.")

    def test_bare_team_word_fails(self) -> None:
        """REQ-006: 'the team' is a generic category, must fire H3."""
        assert q1_aspirational("the team would benefit from this")

    def test_generic_users_fails(self) -> None:
        assert q1_aspirational("users in general would want this")

    def test_future_tense_fails(self) -> None:
        assert q1_aspirational("if users start adopting this we'll need it")

    def test_no_named_entity_fails(self) -> None:
        assert q1_aspirational("there is demand for this feature")


class TestQ3Specific:
    """Direct unit tests for `q3_specific`."""

    def test_named_individual_passes(self) -> None:
        assert q3_specific("Felix on the Bleu rotation, blocked daily.")

    def test_named_rotation_passes(self) -> None:
        assert q3_specific("the SRE on-call hit this last Tuesday.")

    def test_qualified_system_passes(self) -> None:
        assert q3_specific("the auth service in prod-east times out.")

    def test_file_path_passes(self) -> None:
        assert q3_specific("the GraphQL pagination in `get_pr_review_threads.py` is the bottleneck.")

    def test_generic_users_fails(self) -> None:
        assert not q3_specific("users")

    def test_engineers_generic_fails(self) -> None:
        assert not q3_specific("engineers")


class TestQ5Speculative:
    """Direct unit tests for `q5_speculative`."""

    def test_quoted_evidence_passes(self) -> None:
        assert not q5_speculative('Ticket said "deploy timeouts at 504".')

    def test_citation_passes(self) -> None:
        assert not q5_speculative("PR 1887 retro names the gap.")

    def test_named_source_passes(self) -> None:
        assert not q5_speculative("Felix reported three KeyVault timeouts.")

    def test_no_evidence_fails(self) -> None:
        assert q5_speculative("users find this slow")

    def test_vague_belief_fails(self) -> None:
        assert q5_speculative("there is a problem here")


class TestParseHedgePhrases:
    """Direct unit tests for `parse_hedge_phrases`."""

    def test_returns_list(self, spec_text: str) -> None:
        phrases = parse_hedge_phrases(spec_text)
        assert isinstance(phrases, list)
        assert all(isinstance(p, str) for p in phrases)

    def test_required_phrases_present(self, spec_text: str) -> None:
        phrases = parse_hedge_phrases(spec_text)
        for required in ["would be nice", "we believe", "stakeholders want", "probably", "eventually"]:
            assert required in phrases

    def test_no_standalone_words(self, spec_text: str) -> None:
        phrases = parse_hedge_phrases(spec_text)
        for forbidden in ["should", "might", "could"]:
            assert forbidden not in phrases
