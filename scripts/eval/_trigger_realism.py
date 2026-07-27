"""Pure helpers for measuring trigger-phrase realism against real transcripts.

Split from the CLI so the matching and scoring rules are unit-testable without
touching the filesystem or a transcript store.

The matching rules exist because the naive version reports numbers that are
wrong in a specific, documented way:

``word_boundary_match``
    A bare substring test counts ``analyze`` inside ``analyzer`` and inside any
    sentence containing the word. When a practitioner benchmarked a skill
    activation hook, every incorrect hard block traced to a pattern matching
    inside a word, and the errors went to zero once the patterns were anchored.
    See the wiki concept ``Skill Triggering Failure Modes``.

``is_measurable_phrase``
    Two shapes are excluded because a hit tells you nothing about routing.
    A slash command is dispatched by name and never consults a description, so
    counting it measures the dispatcher, not the phrase. A single word is not a
    trigger phrase; it collides with ordinary prose and inflates the score.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType


def is_measurable_phrase(phrase: str) -> bool:
    """Return whether a hit on this phrase would say anything about routing."""
    stripped = phrase.strip()
    if not stripped or stripped.startswith("/"):
        return False
    return len(stripped.split()) >= 2


def word_boundary_match(phrase: str, text: str) -> bool:
    """Return whether the phrase occurs in the text on both word boundaries."""
    stripped = phrase.strip()
    if not stripped:
        return False
    pattern = re.escape(stripped.lower())
    return re.search(rf"(?<!\w){pattern}(?!\w)", text.lower()) is not None


def count_occurrences(phrase: str, corpus: Sequence[str]) -> int:
    """Return how many corpus entries contain the phrase on word boundaries."""
    return sum(1 for entry in corpus if word_boundary_match(phrase, entry))


@dataclass(frozen=True)
class RealismReport:
    """Scored result for one set of phrases against one corpus."""

    measurable: int
    observed: int
    excluded: int
    # Read-only: a mutable mapping on a frozen report could be edited to
    # diverge from the stored ``observed`` and ``realism`` values.
    hits: Mapping[tuple[str, str], int]

    @property
    def realism(self) -> float:
        """Fraction of measurable phrases a real user has ever actually said."""
        if self.measurable == 0:
            return 0.0
        return self.observed / self.measurable


def score(
    phrases_by_skill: dict[str, Iterable[str]], corpus: Sequence[str]
) -> RealismReport:
    """Score every skill's phrases against the corpus.

    A phrase counts as observed when at least one corpus entry contains it on
    word boundaries. Phrases that ``is_measurable_phrase`` rejects are counted
    in ``excluded`` rather than silently dropped, so the denominator is always
    reconstructable from the report.
    """
    measurable = 0
    excluded = 0
    hits: dict[tuple[str, str], int] = {}
    for skill, phrases in phrases_by_skill.items():
        for phrase in phrases:
            if not is_measurable_phrase(phrase):
                excluded += 1
                continue
            measurable += 1
            occurrences = count_occurrences(phrase, corpus)
            if occurrences:
                hits[(skill, phrase)] = occurrences
    return RealismReport(
        measurable=measurable,
        observed=len(hits),
        excluded=excluded,
        hits=MappingProxyType(hits),
    )
