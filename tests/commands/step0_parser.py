"""Parser-side implementation of REQ-006 Step 0 First Principles Gate.

Refs #1926. Used by `tests/commands/test_spec_step0.py`. Implements the
operational tests defined in REQ-006-02 through REQ-006-05 and REQ-006-11
as Python so the gate can be exercised deterministically without an LLM
session.

The parser reads spec.md to extract the canonical hedge phrase list and
applies the operational tests to author-supplied Q1-Q6 answers. It is
NOT a replacement for the model-level enforcement: the gate at runtime
is enforced by the LLM following the spec.md instructions. This parser
exists so tests can pin behavior at CI time.

Public symbols (module-private by underscore convention; the test module
imports them directly):

- `parse_hedge_phrases(spec_text)`
- `hedge_match(answer, phrases)`
- `q1_aspirational(answer)`
- `q3_specific(answer)`
- `q5_speculative(answer)`
- `evaluate_step0(answers, phrases)` — returns halt trigger (`H1..H5`) or `None`
- `baseline_answers()` — fixture data for the canonical "passes" case
- `extract_step0_block`, `extract_step1_paragraph`,
  `extract_tier5_bullet`, `extract_step9_block` — section extractors for
  byte-identical comparison between spec.md and SKILL.md
"""

from __future__ import annotations

import re

# Known technical-term suffixes that follow a hedge word but flip the
# meaning. Example: `eventually consistent` is a load-bearing distributed-
# systems term from .claude/rules/data-intensive-applications.md, not a
# hedge. The suffix set below blocks these from triggering H1.
HEDGE_TECHNICAL_SUFFIXES: dict[str, set[str]] = {
    "eventually": {"consistent", "consistent.", "consistent,"},
}


def parse_hedge_phrases(spec_text: str) -> list[str]:
    """Parse the canonical hedge phrase list out of the Step 0 block.

    The list is rendered as a markdown table with phrases in the first
    column inside backticks. Returns the phrases in source order.
    """
    block_match = re.search(
        r"\*\*Canonical hedge phrase list\*\*.*?\| Phrase.*?\n(.*?)\n\nSingle words",
        spec_text,
        re.DOTALL,
    )
    if block_match is None:
        raise ValueError("hedge phrase table not found in spec.md")
    table = block_match.group(1)
    phrases = re.findall(r"\| `([^`]+)` \|", table)
    if not phrases:
        raise ValueError("no phrases parsed from hedge table")
    return phrases


def hedge_match(answer: str, phrases: list[str]) -> str | None:
    """Return the first hedge phrase matched in the answer, or None.

    Match is case-insensitive AND word-boundary-aware. Phrase-specific
    technical-term suffixes (HEDGE_TECHNICAL_SUFFIXES) flip a hedge match
    to a non-match — `eventually consistent` is a technical term, not a
    hedge.
    """
    lower = answer.lower()
    for phrase in phrases:
        pattern = r"\b" + re.escape(phrase.lower()) + r"\b"
        for match in re.finditer(pattern, lower):
            suffixes = HEDGE_TECHNICAL_SUFFIXES.get(phrase.lower(), set())
            after = lower[match.end():].lstrip()
            first_word = after.split(maxsplit=1)[0] if after else ""
            if first_word in suffixes:
                continue
            return phrase
    return None


def q1_aspirational(answer: str) -> bool:
    """REQ-006-04 operational test: any one condition makes Q1 aspirational.

    Three conditions; any one fires:
    1. No specific named entity (person, team name, system, ticket, file).
    2. Future tense or conditional mood about demand existence.
    3. Generic category ("the team", "stakeholders", "users in general").

    The named-entity detector requires a named team (capitalized noun
    immediately preceding `team`/`service`/`squad`/`rotation`) — bare
    `team` is NOT a positive signal because "the team" is itself a
    generic category that should fail Q1.
    """
    lower = answer.lower()
    has_named_entity = bool(
        re.search(
            r"#\d+|"
            r"[A-Z][a-z]+ on the |"
            r"[A-Z][a-z]+ (team|service|squad|rotation)|"
            r"\.py\b|\.md\b|\.json\b|\.yml\b|\.yaml\b|"
            r"\bPR \d+|\bissue \d+",
            answer,
        )
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


def q3_specific(answer: str) -> bool:
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


def q5_speculative(answer: str) -> bool:
    """REQ-006-03 operational test: speculative if all three branches absent."""
    has_quote = '"' in answer or "```" in answer
    has_citation = bool(
        re.search(r"#\d+|PR\s*\d+|issue\s*\d+|`[^`]+`|line\s*\d+", answer, re.IGNORECASE)
    )
    has_named_source = bool(
        re.search(r"\b[A-Z][a-z]+\s+(said|reported|escalated|filed)\b", answer)
    )
    return not (has_quote or has_citation or has_named_source)


def evaluate_step0(answers: dict[str, str], phrases: list[str]) -> str | None:
    """Return halt trigger ID (H1..H5) or None if Step 0 passes.

    Trigger order: H5 (partial) > H1 (hedge) > H2 (Q5 speculative) >
    H3 (Q1 aspirational) > H4 (Q3 generic). The order is deterministic;
    the first trigger to fire is returned.
    """
    if not all(answers.get(q) for q in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]):
        return "H5"
    for value in answers.values():
        if hedge_match(value, phrases):
            return "H1"
    if q5_speculative(answers["Q5"]):
        return "H2"
    if q1_aspirational(answers["Q1"]):
        return "H3"
    if not q3_specific(answers["Q3"]):
        return "H4"
    return None


def baseline_answers() -> dict[str, str]:
    """Canonical "passes" answer set used as a fixture in tests."""
    return {
        "Q1": "Three teams (Bleu, Delos, Calc) escalated KeyVault deploy failures in #1700, #1820, #1850.",
        "Q2": "Engineers manually retry deploys 3 times before opening a ticket.",
        "Q3": "Felix on the Bleu rotation, blocked on KeyVault deploys, three times last week.",
        "Q4": "Add retry-with-backoff to the deploy script, ~4 hours.",
        "Q5": "Issue #1700 line 12 reports `KeyVault timeout (504)` on three deploys.",
        "Q6": "At 10x scale, the retry adds bounded latency (~30s) and stays useful.",
    }


def extract_step0_block(text: str) -> str:
    match = re.search(
        r"### Step 0:.*?(?=\n1\. Clarify the problem)", text, re.DOTALL
    )
    if match is None:
        raise ValueError("Step 0 block not found")
    return match.group(0)


def extract_step1_paragraph(text: str) -> str:
    match = re.search(
        r"\n1\. Clarify the problem.*?(?=\n2\. )", text, re.DOTALL
    )
    if match is None:
        raise ValueError("Step 1 paragraph not found")
    return match.group(0)


def extract_tier5_bullet(text: str) -> str:
    match = re.search(r"   - Tier 5 \(Principal\):.*?$", text, re.MULTILINE)
    if match is None:
        raise ValueError("Tier 5 bullet not found")
    return match.group(0)


def extract_step9_block(text: str) -> str:
    match = re.search(
        r"\n9\. Task\(subagent_type=\"critic\"\).*?(?=\n## )", text, re.DOTALL
    )
    if match is None:
        raise ValueError("Step 9 block not found")
    return match.group(0)
