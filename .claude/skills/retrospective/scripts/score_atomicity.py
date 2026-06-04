#!/usr/bin/env python3
"""Score a retrospective learning 0-100 for atomicity.

Pure scoring function plus a CLI. Phase 4 of the retrospective workflow scores
every extracted learning and rejects vague statements before they reach memory.

Canonical source: the deduction table and quality thresholds are lifted verbatim
from ``.claude/skills/retrospective/references/diagnosis-and-actions.md``
(section "Atomicity Scoring", lines 199-218). That reference in turn quotes the
agent body at ``.claude/agents/retrospective.md``. Quoted contract:

    | Factor | Adjustment |
    |--------|------------|
    | Compound statements ("and", "also") | -15% each |
    | Vague terms ("generally", "sometimes") | -20% each |
    | Length > 15 words | -5% per extra word |
    | Missing metrics/evidence | -25% |
    | No actionable guidance | -30% |

    ### Quality Thresholds

    | Score | Quality | Action |
    |-------|---------|--------|
    | 95-100% | Excellent | Add to skillbook |
    | 70-94% | Good | Add with refinement |
    | 40-69% | Needs Work | Refine before adding |
    | <40% | Rejected | Too vague |

Stricter/looser/different than canonical: none. The score starts at 100 and the
deductions clamp to the 0-100 range. The reference does not enumerate the exact
trigger words for "compound" and "vague"; this module fixes a concrete word list
(``and``, ``also`` for compound; ``generally``, ``sometimes``, ``effective``,
``effectively``, ``good``, ``better``, ``well`` for vague) so the score is
deterministic and testable. The list includes ``effective`` because the canonical
worked example scores "The caching strategy was effective" as vague (lines
222-226 of the reference). The 70 percent persistence threshold used by the
SKILL.md Phase 5 contract is the boundary of the "Good" band above.

Exit codes (ADR-035):
  0: learning scored at or above the 70% persistence threshold
  1: learning scored below the 70% persistence threshold (refine or reject)
  2: usage or configuration error (missing argument, empty learning)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass

# Persistence threshold from SKILL.md Phase 5: learnings at or above this score
# are persisted to memory; the "Good" band in the canonical thresholds starts
# here.
PERSISTENCE_THRESHOLD = 70

# Compound markers cost 15% each (canonical deduction table).
_COMPOUND_WORDS = ("and", "also")
# Vague markers cost 20% each (canonical deduction table). "effective" and the
# other quality-judgment adjectives are included because the canonical worked
# example treats "The caching strategy was effective" as vague.
_VAGUE_WORDS = (
    "generally",
    "sometimes",
    "effective",
    "effectively",
    "good",
    "better",
    "well",
)
# Length above this word count costs 5% per extra word (canonical table).
_MAX_WORDS = 15
# Missing metrics/evidence costs 25% (canonical table).
_MISSING_EVIDENCE_PENALTY = 25
# No actionable guidance costs 30% (canonical table).
_NO_ACTION_PENALTY = 30


@dataclass(frozen=True, slots=True)
class AtomicityScore:
    """Structured atomicity result.

    Attributes:
        score: Final atomicity score, clamped to 0-100.
        quality: Quality band label from the canonical thresholds.
        compound_terms: Compound markers found in the learning.
        vague_terms: Vague markers found in the learning.
        word_count: Word count of the learning.
        has_metrics: Whether the learning carries a numeric metric.
        is_actionable: Whether the learning gives actionable guidance.
        breakdown: Per-factor point deductions for transparency.
    """

    score: int
    quality: str
    compound_terms: list[str]
    vague_terms: list[str]
    word_count: int
    has_metrics: bool
    is_actionable: bool
    breakdown: dict[str, int]


def _count_word_occurrences(text_lower: str, words: tuple[str, ...]) -> list[str]:
    """Return the markers from ``words`` present in ``text_lower``, with repeats.

    Whole-word matching avoids counting ``and`` inside ``standard`` or
    ``sometimes`` inside an unrelated token.
    """
    found: list[str] = []
    for word in words:
        # Count whole-word, case-insensitive occurrences.
        matches = re.findall(rf"\b{re.escape(word)}\b", text_lower)
        found.extend(matches)
    return found


def _has_metrics(text: str) -> bool:
    """Detect a numeric metric (a digit run, percentage, or duration token)."""
    return bool(re.search(r"\d", text))


_NON_ACTIONABLE = re.compile(
    r"^(the|it|this|that|there)\b.*\b(was|were|is|are|seemed|felt)\b",
    re.IGNORECASE,
)
_ACTIONABLE_COPULA = re.compile(
    r"^(the|it|this|that|there)\b.*\b(was|were|is|are)\s+to\b",
    re.IGNORECASE,
)


def _is_actionable(text: str) -> bool:
    """Heuristic for actionable guidance.

    A learning is actionable when it does more than describe a past feeling or
    state. Statements shaped like "The caching strategy was effective" describe
    an outcome without telling a future reader what to do, so they fail.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _ACTIONABLE_COPULA.match(stripped):
        return True
    # Pure description of a past state ("X was effective") is not actionable.
    return _NON_ACTIONABLE.match(stripped) is None


def _quality_band(score: int) -> str:
    """Map a score to the canonical quality band label."""
    if score >= 95:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 40:
        return "Needs Work"
    return "Rejected"


def score_learning(learning: str) -> AtomicityScore:
    """Score a learning statement 0-100 for atomicity.

    Applies the canonical deduction table to a base of 100 and clamps the
    result to the 0-100 range. Returns a structured breakdown so callers can
    explain why a learning was refined or rejected.

    Args:
        learning: The learning statement to score.

    Returns:
        An :class:`AtomicityScore` with the final score and per-factor detail.

    Raises:
        ValueError: If ``learning`` is empty or whitespace only.
    """
    if not learning or not learning.strip():
        raise ValueError("learning must be a non-empty string")

    text = learning.strip()
    text_lower = text.lower()

    compound_terms = _count_word_occurrences(text_lower, _COMPOUND_WORDS)
    vague_terms = _count_word_occurrences(text_lower, _VAGUE_WORDS)
    word_count = len(text.split())
    has_metrics = _has_metrics(text)
    is_actionable = _is_actionable(text)

    breakdown: dict[str, int] = {}

    compound_penalty = len(compound_terms) * 15
    if compound_penalty:
        breakdown["compound"] = compound_penalty

    vague_penalty = len(vague_terms) * 20
    if vague_penalty:
        breakdown["vague"] = vague_penalty

    extra_words = max(0, word_count - _MAX_WORDS)
    length_penalty = extra_words * 5
    if length_penalty:
        breakdown["length"] = length_penalty

    if not has_metrics:
        breakdown["missing_evidence"] = _MISSING_EVIDENCE_PENALTY

    if not is_actionable:
        breakdown["no_action"] = _NO_ACTION_PENALTY

    raw = 100 - sum(breakdown.values())
    score = max(0, min(100, raw))

    return AtomicityScore(
        score=score,
        quality=_quality_band(score),
        compound_terms=compound_terms,
        vague_terms=vague_terms,
        word_count=word_count,
        has_metrics=has_metrics,
        is_actionable=is_actionable,
        breakdown=breakdown,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Score a retrospective learning 0-100 for atomicity.",
    )
    parser.add_argument(
        "learning",
        nargs="?",
        help="The learning statement to score. Reads stdin when omitted.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full score breakdown as JSON.",
    )
    return parser


def _read_learning(arg: str | None) -> str:
    """Resolve the learning text from the argument or stdin."""
    if arg is not None:
        return arg
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    learning = _read_learning(args.learning)
    if not learning or not learning.strip():
        print("ERROR: no learning provided (pass an argument or pipe stdin)", file=sys.stderr)
        return 2

    result = score_learning(learning)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"Atomicity: {result.score}% ({result.quality})")
        if result.breakdown:
            print("Deductions:")
            for factor, points in result.breakdown.items():
                print(f"  {factor}: -{points}%")

    return 0 if result.score >= PERSISTENCE_THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main())
