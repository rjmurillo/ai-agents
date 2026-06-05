"""Parser-side implementation of REQ-016 Step 0 First Principles Gate.

Refs #1926. Used by `tests/commands/test_spec_step0.py`. Implements the
operational tests defined in REQ-016-02 through REQ-016-05 and REQ-016-11
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
- `evaluate_step0(answers, phrases)`: returns halt trigger (`H1..H5`) or `None`
- `baseline_answers()`: fixture data for the canonical "passes" case
- `extract_step0_block`, `extract_step1_paragraph`,
  `extract_tier5_bullet`, `extract_step9_block`: section extractors for
  byte-identical comparison between spec.md and SKILL.md
"""

from __future__ import annotations

import re

# Known technical-term suffixes that follow a hedge word but flip the
# meaning. Example: `eventually consistent` and `eventually-consistent`
# are load-bearing distributed-systems terms from .claude/rules/
# data-intensive-applications.md, not hedges. The suffix set below
# blocks both space-separated and hyphenated forms (cursor PR #1931
# comment 3213964377). `hedge_match` strips leading whitespace AND
# hyphens before extracting the suffix word, so `-consistent` from
# "eventually-consistent" normalizes to `consistent`.
HEDGE_TECHNICAL_SUFFIXES: dict[str, set[str]] = {
    # Bare word, plus common trailing punctuation that would otherwise
    # break the suffix lookup (devin PR #1931 review comment 3213978113).
    "eventually": {
        "consistent",
        "consistent.",
        "consistent,",
        "consistent;",
        "consistent:",
        "consistent)",
        "consistent!",
        "consistent?",
    },
}


def parse_hedge_phrases(spec_text: str) -> list[str]:
    """Parse the canonical hedge phrase list out of the Step 0 block.

    The list is rendered as a markdown table with phrases in the first
    column inside backticks. The table boundary is anchored on a stable
    HTML-comment sentinel `<!-- step0:hedge-table-end -->` rather than
    surrounding prose; the sentinel is invisible in rendered markdown
    but visible to this parser. Returns the phrases in source order.
    """
    block_match = re.search(
        r"\*\*Canonical hedge phrase list\*\*.*?\| Phrase.*?\n(.*?)\n<!-- step0:hedge-table-end -->",
        spec_text,
        re.DOTALL,
    )
    if block_match is None:
        raise ValueError(
            "hedge phrase table not found in spec.md "
            "(expected `<!-- step0:hedge-table-end -->` sentinel)"
        )
    table = block_match.group(1)
    phrases = re.findall(r"\| `([^`]+)` \|", table)
    if not phrases:
        raise ValueError("no phrases parsed from hedge table")
    return phrases


def hedge_match(answer: str, phrases: list[str]) -> str | None:
    """Return the first hedge phrase matched in the answer, or None.

    Match is case-insensitive AND word-boundary-aware. Phrase-specific
    technical-term suffixes (HEDGE_TECHNICAL_SUFFIXES) flip a hedge match
    to a non-match. `eventually consistent` is a technical term, not a
    hedge.
    """
    lower = answer.lower()
    for phrase in phrases:
        pattern = r"\b" + re.escape(phrase.lower()) + r"\b"
        for match in re.finditer(pattern, lower):
            suffixes = HEDGE_TECHNICAL_SUFFIXES.get(phrase.lower(), set())
            after = lower[match.end():].lstrip(" \t-")
            first_word = after.split(maxsplit=1)[0] if after else ""
            if first_word in suffixes:
                continue
            return phrase
    return None


def q1_aspirational(answer: str) -> bool:
    """REQ-016-04 operational test: any one of three conditions makes Q1 aspirational.

    Three conditions; any one fires:
    1. Fewer than three specific named entities (person, team name, system, ticket, file).
    2. Future tense or conditional mood about demand existence.
    3. Generic category appearing WITHOUT a specific named entity (so
       "the team would benefit" fires; "Bleu team, Delos team, and
       Calc team escalated #1700" does not, because four specific
       entities (three teams + one ticket) satisfy the >= 3 threshold
       in condition 1 and the named-entity check in condition 3).

    Restored generic-category condition #3 per Copilot PR #1931 comments
    3213975262 + 3213984488 (round-4 finding): the round-1 simplification
    dropped this branch; the docstring claimed three conditions while the
    code only checked two. Now matches the spec.md operational test.

    Named-entity detector recognizes: `Person on the X`, `Capitalized
    team/service/squad/rotation` (where Capitalized accepts PascalCase
    like `KeyVault` and acronyms like `SRE` via `[A-Z][a-zA-Z]*`),
    ticket numbers (`#123`, `PR 123`, `issue 123`), and file paths
    (`.py`, `.md`, `.json`, `.yml`, `.yaml`, with or without backticks).
    """
    lower = answer.lower()
    cap_id = r"[A-Z][a-zA-Z]*"
    team_suffix = r"(?:team|service|squad|rotation)"
    entity_pattern = (
        r"#\d+|"
        rf"{cap_id} on (?:the )?{cap_id} {team_suffix}|"
        rf"{cap_id} {team_suffix}|"
        r"\.py\b|\.md\b|\.json\b|\.yml\b|\.yaml\b|"
        r"\bPR \d+|\bissue \d+"
    )
    entity_matches = re.findall(entity_pattern, answer)
    named_entity_count = len(entity_matches)
    has_named_entity = named_entity_count > 0
    # Q1 aspirational condition 1 per spec.md and REQ-016-04: "fewer
    # than three specific requesters". A single named requester is not
    # enough (Copilot PR #1931 comments 3214013611, 3214013621; devin
    # 3214020363).
    has_too_few_requesters = named_entity_count < 3
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
    is_generic = (not has_named_entity) and any(
        re.search(r"\b" + re.escape(marker) + r"\b", lower)
        for marker in [
            "users in general",
            "engineers in general",
            "the team",
            "stakeholders",
            "developers in general",
            "all users",
            "engineers",
            "developers",
        ]
    )
    return has_future_or_conditional or has_too_few_requesters or is_generic


def q3_specific(answer: str) -> bool:
    """REQ-016-05 operational test: must satisfy at least one specificity branch.

    Three branches; any one passes:
    1. Named individual: `Alice on the Payments team`.
    2. Named team or rotation: any `rotation`/`on-call`/`squad`/`team`
       qualifier with a preceding identifier (capitalized name OR an
       acronym-style ALL-CAPS token like `SRE`). Spec.md gives both
       `Felix on the Bleu/Delos rotation` (capitalized) and
       `the SRE on-call` (acronym) as valid examples; both must pass.
    3. Qualified system or component: `in prod-east`, `vN` version,
       `path/to/file.py`, `path/to/file.md`.
    """
    has_named_individual = bool(
        re.search(
            # Same trailing-team-suffix gate as q1_aspirational to prevent
            # "Based on the evidence" or "Reflected on the data" from
            # matching (cursor PR #1931 commit f21777a6 + comment 3213953383).
            # Slash-separated team names (`Bleu/Delos rotation`) are
            # supported via the `(?:/[A-Z][a-zA-Z]*)*` alternation
            # (devin PR #1931 comment 3214020343).
            r"\b[A-Z][a-zA-Z]* on (?:the )?[A-Z][a-zA-Z]*(?:/[A-Z][a-zA-Z]*)* (?:team|service|squad|rotation)",
            answer,
        )
    )
    # Named-team: either `the <CapId>` (definite article + capitalized
    # team identifier) OR a bare acronym (`SRE`, `QA`), IMMEDIATELY
    # followed by a team-keyword. Bare `[A-Z][a-zA-Z]*` would match
    # sentence-initial `The` or `Storage`, causing false positives;
    # the definite article requirement gates these out (cursor PR #1931
    # commit 3cca172f + comment 3213988623).
    has_named_team = bool(
        re.search(
            r"\b(?:the (?:[A-Z][a-zA-Z]*(?:/[A-Z][a-zA-Z]*)*|[A-Z]{2,})|[A-Z]{2,}) "
            r"(?:rotation|on-call|squad|team|service)\b",
            answer,
        )
    )
    # Qualified system: word-bounded environment qualifiers (prevents
    # `in deviation` from matching `in dev`. devin PR #1931 comment
    # 3213990126), version `vN`, or file path with optional backticks
    # (Copilot/cursor PR #1931 comments 3213984514 + 3213988625;
    # spec.md example uses unquoted `get_pr_review_threads.py`).
    has_qualified_system = bool(
        re.search(
            r"\bin (?:prod-[a-z]+|staging|dev|test)\b|"
            r"\bv\d+\b|"
            r"`?\b[\w./-]+\.(?:py|md|json|yml|yaml)\b`?",
            answer,
        )
    )
    return has_named_individual or has_named_team or has_qualified_system


def q5_speculative(answer: str) -> bool:
    """REQ-016-03 operational test: speculative if all three branches absent.

    Q5 passes if any one of:
    1. Answer contains a direct quote (text in `"..."` or fenced block).
    2. Answer cites a metric, log entry, file path, commit SHA, PR
       number, or named artifact.
    3. Answer names a specific person, team, or system that described
       the problem.

    Per Copilot PR #1931 comment 3213984505: condition 3 was previously
    `[A-Z][a-z]+ (said|reported|escalated|filed)` (person + verb), which
    rejected named teams/systems. Now also recognizes named teams and
    PascalCase systems via the same `[A-Z][a-zA-Z]*` pattern q1 uses.
    """
    has_quote = '"' in answer or "```" in answer
    has_citation = bool(
        re.search(
            r"#\d+|PR\s*\d+|issue\s*\d+|`[^`]+`|line\s*\d+|"
            # Bare file paths (path/file.py, file.md) without backticks.
            r"\b[\w./-]+\.(?:py|md|json|yml|yaml)\b",
            answer,
            re.IGNORECASE,
        )
    )
    # Named source: capitalized identifier (person, team, or PascalCase
    # system) followed by a reporting verb. Accepts "Felix reported",
    # "Bleu team escalated", "KeyVault timed out", "the SRE on-call filed".
    has_named_source = bool(
        re.search(
            r"\b(?:[A-Z][a-zA-Z]*|[A-Z]{2,})(?:\s+\w+){0,3}\s+"
            r"(?:said|reported|escalated|filed|timed|errored|crashed|failed|exceeded)\b",
            answer,
        )
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
    """Extract the entire Tier 5 bullet, anchored on the next sibling
    bullet (`   - Tier `) or a blank-line terminator. Greedy match to
    end-of-line is insufficient because the bullet may wrap across
    physical lines."""
    match = re.search(
        r"   - Tier 5 \(Principal\):.*?(?=\n   - Tier |\n\n|\n4\. )",
        text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("Tier 5 bullet not found")
    return match.group(0)


def extract_step9_block(text: str) -> str:
    """Extract the Step 9 block, anchored on the next H2 heading OR
    end-of-file. Files that end with the Step 9 block (no trailing H2)
    are also handled. The opener is anchored on `\\n9. ` (any step-9 opening
    line), not the specific `Task(subagent_type="critic")` wording, so
    rephrasing the step's first sentence does not break the extractor."""
    match = re.search(
        r"\n9\. .*?(?=\n## |\Z)",
        text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("Step 9 block not found")
    return match.group(0)
