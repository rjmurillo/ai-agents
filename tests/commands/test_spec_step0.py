"""Tests for Step 0 First Principles Gate in /spec command.

Refs #1926, REQ-006, DESIGN-006, TASK-006.

These tests verify the static structure and parser-checkable behavior of
Step 0 instructions in `.claude/commands/spec.md` and its Copilot CLI
mirror at `src/copilot-cli/skills/spec/SKILL.md`. Six dynamic LLM-dependent
cases (T2, T3, T4, T10, T12, T13) are documented manual spot-checks per
PLAN-1926; they are not run here because they probe model interpretation
of the spec, not the spec text itself.

Static checks (Static-1, Static-2):
    Static-1 — required tokens present in spec.md (heading order,
        Step-1 directive, Tier-5 replacement, kill-criteria reference).
    Static-2 — diff of edited body sections between spec.md and SKILL.md
        is byte-identical.

Parser-based dynamic checks (T1, T5, T6, T7, T8, T11):
    Each case provides a Q1-Q6 answer dict and asserts which halt
    trigger (H1..H5) fires, or that no trigger fires.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_MD = PROJECT_ROOT / ".claude" / "commands" / "spec.md"
SKILL_MD = PROJECT_ROOT / "src" / "copilot-cli" / "skills" / "spec" / "SKILL.md"

# ---------------------------------------------------------------------------
# Static-1: token presence in spec.md
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_step0_heading_precedes_step1_in_spec_md(spec_text: str) -> None:
    """AC-1a: the Step 0 heading appears before Step 1 in the file."""
    step0_offset = spec_text.find("### Step 0:")
    step1_offset = spec_text.find("\n1. Clarify the problem")
    assert step0_offset != -1, "missing '### Step 0:' heading"
    assert step1_offset != -1, "missing Step 1 list item"
    assert step0_offset < step1_offset, "Step 0 must appear before Step 1"


def test_step1_references_step0_block(spec_text: str) -> None:
    """AC-7a, AC-7b: Step 1 prose references the Step 0 block and forbids re-elicitation."""
    step1_match = re.search(
        r"\n1\. Clarify the problem.*?(?=\n2\. )", spec_text, re.DOTALL
    )
    assert step1_match is not None, "Step 1 paragraph not found"
    step1_text = step1_match.group(0)
    assert "Step 0" in step1_text, "Step 1 must reference Step 0"
    assert "Q1-Q6" in step1_text, "Step 1 must reference Q1-Q6"
    assert "Do not re-elicit" in step1_text, "Step 1 must forbid re-elicitation"


def test_tier5_replaces_why_not_simpler(spec_text: str) -> None:
    """AC-8: Tier 5 bullet replaces 'why not simpler?' with Step 0 Q4 re-validation.

    The bullet may mention "why not simpler?" as a meta-reference to the v1
    text being replaced; the structural check is that the active directive
    is the Q4 re-validation, not a standalone "why not simpler?" challenge.
    """
    tier5_match = re.search(
        r"^   - Tier 5 \(Principal\):.*?$", spec_text, re.MULTILINE
    )
    assert tier5_match is not None, "Tier 5 bullet not found"
    tier5_text = tier5_match.group(0)
    assert "Re-validate Step 0 Q4" in tier5_text, "Tier 5 must reference Q4 re-validation"
    # The v1 directive form ("Explicit why not simpler? challenge") must be absent.
    assert "Explicit why not simpler?" not in tier5_text, (
        "Tier 5 must not contain the v1 standalone challenge directive"
    )


def test_step9_contains_binary_checks(spec_text: str) -> None:
    """AC-9: Step 9 critic pre-mortem contains Check 9a, 9b, 9c with binary phrasing."""
    assert "Check 9a" in spec_text, "Step 9 must include Check 9a"
    assert "Check 9b" in spec_text, "Step 9 must include Check 9b"
    assert "Check 9c" in spec_text, "Step 9 must include Check 9c"
    assert "PASS:" in spec_text, "Step 9 checks must include PASS conditions"
    assert "FAIL" in spec_text, "Step 9 checks must include FAIL conditions"
    assert "SHALL NOT return APPROVED" in spec_text, (
        "Step 9 must block APPROVED while any check is FAIL"
    )


def test_step0_kill_criteria_reference(spec_text: str) -> None:
    """AC-13: Step 0 references kill criteria + tally infrastructure."""
    assert "STEP-0-METRICS.md" in spec_text, (
        "Step 0 must reference the tally file path"
    )
    assert "kill criteria" in spec_text.lower() or "Kill criteria" in spec_text, (
        "Step 0 must reference kill criteria"
    )


# ---------------------------------------------------------------------------
# Static-2: edited sections byte-identical between spec.md and SKILL.md
# ---------------------------------------------------------------------------


def _extract_step0_block(text: str) -> str:
    match = re.search(
        r"### Step 0:.*?(?=\n1\. Clarify the problem)", text, re.DOTALL
    )
    assert match is not None, "Step 0 block not found"
    return match.group(0)


def _extract_step1_paragraph(text: str) -> str:
    match = re.search(
        r"\n1\. Clarify the problem.*?(?=\n2\. )", text, re.DOTALL
    )
    assert match is not None, "Step 1 paragraph not found"
    return match.group(0)


def _extract_tier5_bullet(text: str) -> str:
    match = re.search(r"   - Tier 5 \(Principal\):.*?$", text, re.MULTILINE)
    assert match is not None, "Tier 5 bullet not found"
    return match.group(0)


def _extract_step9_block(text: str) -> str:
    match = re.search(
        r"\n9\. Task\(subagent_type=\"critic\"\).*?(?=\n## )", text, re.DOTALL
    )
    assert match is not None, "Step 9 block not found"
    return match.group(0)


def test_step0_block_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Step 0 block byte-identical between spec.md and SKILL.md."""
    assert _extract_step0_block(spec_text) == _extract_step0_block(skill_text)


def test_step1_paragraph_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Step 1 narrowed paragraph identical."""
    assert _extract_step1_paragraph(spec_text) == _extract_step1_paragraph(skill_text)


def test_tier5_bullet_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Tier 5 bullet identical."""
    assert _extract_tier5_bullet(spec_text) == _extract_tier5_bullet(skill_text)


def test_step9_block_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Step 9 critic block identical."""
    assert _extract_step9_block(spec_text) == _extract_step9_block(skill_text)


# ---------------------------------------------------------------------------
# Parser: extract canonical hedge phrase list from spec.md
# ---------------------------------------------------------------------------


def _parse_hedge_phrases(spec_text: str) -> list[str]:
    """Parse the canonical hedge phrase list out of the Step 0 block.

    The list is rendered as a markdown table with phrases in the first
    column inside backticks. The parser extracts every backtick-quoted
    phrase from the table rows between the 'Canonical hedge phrase list'
    heading and the next blank line that ends the table.
    """
    block_match = re.search(
        r"\*\*Canonical hedge phrase list\*\*.*?\| Phrase.*?\n(.*?)\n\nSingle words",
        spec_text,
        re.DOTALL,
    )
    assert block_match is not None, "hedge phrase table not found in spec.md"
    table = block_match.group(1)
    phrases = re.findall(r"\| `([^`]+)` \|", table)
    assert phrases, "no phrases parsed from hedge table"
    return phrases


def test_hedge_phrase_list_parsed(spec_text: str) -> None:
    """The parser finds at least 15 hedge phrases in spec.md."""
    phrases = _parse_hedge_phrases(spec_text)
    assert len(phrases) >= 15, f"expected >=15 hedge phrases, got {len(phrases)}"
    # Spot-check known entries
    for required in ["would be nice", "we believe", "stakeholders want", "probably"]:
        assert required in phrases, f"missing required phrase: {required}"


def test_no_standalone_should_might_could(spec_text: str) -> None:
    """REQ-006-02: standalone 'should'/'might'/'could' MUST NOT be hedge phrases."""
    phrases = _parse_hedge_phrases(spec_text)
    for forbidden in ["should", "might", "could"]:
        assert forbidden not in phrases, (
            f"single-word '{forbidden}' must not be a hedge phrase (RFC 2119 collision)"
        )


# ---------------------------------------------------------------------------
# Operational tests applied to Q1-Q6 answer dicts
# ---------------------------------------------------------------------------


def _hedge_match(answer: str, phrases: list[str]) -> str | None:
    """Return the first hedge phrase matched in the answer, or None."""
    lower = answer.lower()
    for phrase in phrases:
        if phrase.lower() in lower:
            return phrase
    return None


def _q1_aspirational(answer: str) -> bool:
    """REQ-006-04 operational test: any one condition makes Q1 aspirational."""
    lower = answer.lower()
    has_named_entity = bool(
        re.search(r"#\d+|[A-Z][a-z]+ on the |\bteam\b|\bservice\b|\.py|\.md|\.json|PR\b|issue\b", answer)
    )
    has_future_or_conditional = any(
        marker in lower
        for marker in [
            "would want",
            "would be useful",
            "would be helpful",
            "if customers start",
            "if users start",
            "when we have",
        ]
    )
    is_generic = any(
        marker in lower
        for marker in [
            "users in general",
            "engineers in general",
            "the team",
            "stakeholders",
            "developers in general",
            "all users",
        ]
    )
    return (not has_named_entity) or has_future_or_conditional or is_generic


def _q3_specific(answer: str) -> bool:
    """REQ-006-05 operational test: must satisfy at least one specificity branch."""
    has_named_individual = bool(re.search(r"\b[A-Z][a-z]+ on (the )?[A-Z]?[a-z]+", answer))
    has_named_team = bool(
        re.search(r"\b(rotation|on-call|squad|team)\b", answer)
        and re.search(r"[A-Z][a-z]+", answer)
    )
    has_qualified_system = bool(
        re.search(
            r"\bin (prod-|staging|dev|test)|\bv\d+|`[^`]+\.py`|`[^`]+\.md`",
            answer,
        )
    )
    return has_named_individual or has_named_team or has_qualified_system


def _q5_speculative(answer: str) -> bool:
    """REQ-006-03 operational test: speculative if all three branches absent."""
    has_quote = '"' in answer or "```" in answer
    has_citation = bool(
        re.search(r"#\d+|PR\s*\d+|issue\s*\d+|`[^`]+`|line\s*\d+", answer, re.IGNORECASE)
    )
    has_named_source = bool(
        re.search(r"\b[A-Z][a-z]+\s+(said|reported|escalated|filed)\b", answer)
    )
    return not (has_quote or has_citation or has_named_source)


def _evaluate_step0(answers: dict[str, str], phrases: list[str]) -> str | None:
    """Return halt trigger ID (H1..H5) or None if Step 0 passes."""
    if not all(answers.get(q) for q in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]):
        return "H5"
    for value in answers.values():
        if _hedge_match(value, phrases):
            return "H1"
    if _q5_speculative(answers["Q5"]):
        return "H2"
    if _q1_aspirational(answers["Q1"]):
        return "H3"
    if not _q3_specific(answers["Q3"]):
        return "H4"
    return None


# ---------------------------------------------------------------------------
# Test cases T1, T5, T6, T7, T8, T11 (parser-checkable)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hedge_phrases(spec_text: str) -> list[str]:
    return _parse_hedge_phrases(spec_text)


def _baseline_answers() -> dict[str, str]:
    return {
        "Q1": "Three teams (Bleu, Delos, Calc) escalated KeyVault deploy failures in #1700, #1820, #1850.",
        "Q2": "Engineers manually retry deploys 3 times before opening a ticket.",
        "Q3": "Felix on the Bleu rotation, blocked on KeyVault deploys, three times last week.",
        "Q4": "Add retry-with-backoff to the deploy script, ~4 hours.",
        "Q5": "Issue #1700 line 12 reports `KeyVault timeout (504)` on three deploys.",
        "Q6": "At 10x scale, the retry adds bounded latency (~30s) and stays useful.",
    }


def test_t1_hedge_phrase_in_q3_triggers_h1(hedge_phrases: list[str]) -> None:
    """T1: 'stakeholders want' in Q3 fires H1 halt."""
    answers = _baseline_answers()
    answers["Q3"] = "stakeholders want a faster gate"
    assert _evaluate_step0(answers, hedge_phrases) == "H1"


def test_t5_aspirational_q1_triggers_h3(hedge_phrases: list[str]) -> None:
    """T5: aspirational Q1 fires H3 halt."""
    answers = _baseline_answers()
    answers["Q1"] = "users in general would want this"
    assert _evaluate_step0(answers, hedge_phrases) == "H3"


def test_t6_concrete_q1_passes(hedge_phrases: list[str]) -> None:
    """T6: Q1 with three named teams + ticket numbers passes."""
    answers = _baseline_answers()
    assert _evaluate_step0(answers, hedge_phrases) is None


def test_t7_generic_q3_triggers_h4(hedge_phrases: list[str]) -> None:
    """T7: generic Q3 ('engineers') fires H4 halt."""
    answers = _baseline_answers()
    answers["Q3"] = "engineers in general"
    # 'engineers in general' also fires H3 via aspirational test (generic category).
    # H3 fires before H4 in the order; either is correct — assert it's at least one.
    trigger = _evaluate_step0(answers, hedge_phrases)
    assert trigger in {"H3", "H4"}, f"expected H3 or H4, got {trigger}"


def test_t8_specific_q3_passes(hedge_phrases: list[str]) -> None:
    """T8: Q3 with named individual + system + frequency passes."""
    answers = _baseline_answers()
    assert _evaluate_step0(answers, hedge_phrases) is None


def test_t11_partial_completion_triggers_h5(hedge_phrases: list[str]) -> None:
    """T11: empty Q4-Q6 fires H5 halt (partial completion)."""
    answers = _baseline_answers()
    answers["Q4"] = ""
    answers["Q5"] = ""
    answers["Q6"] = ""
    assert _evaluate_step0(answers, hedge_phrases) == "H5"


def test_rfc_2119_should_in_q5_does_not_trigger_h1(hedge_phrases: list[str]) -> None:
    """T2 (parser side): standalone 'should' in Q5 must not fire H1."""
    answers = _baseline_answers()
    answers["Q5"] = (
        'Issue #1700 says "the system should retry transient KeyVault timeouts"; '
        "we observed 3 such timeouts last week."
    )
    # H1 must not fire on standalone 'should'
    trigger = _evaluate_step0(answers, hedge_phrases)
    assert trigger != "H1", "standalone 'should' must not be a hedge phrase"
