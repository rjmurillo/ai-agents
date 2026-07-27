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

Provenance
----------

Read this before citing any figure this eval produces.

The corpus is the measurement. This eval reported three different wrong numbers
before it reported a right one, and every failure was a corpus defect that the
code could not see:

1. It counted tool results as user prompts, because tool output shares the
   ``user`` role in the transcript format.
2. It counted agent-authored subagent prompts as operator prompts, because
   those also carry the ``user`` role.
3. It counted harness-injected envelopes as prose. After excluding meta and
   sidechain entries, 154 of 163 remaining unique texts began with ``<``, and
   the survivors were mostly compaction boilerplate. Roughly one genuine human
   utterance was left.

Two consequences are encoded here rather than left to a reviewer.

``NON_HUMAN_ENTRY_FLAGS`` / ``NON_HUMAN_PROMPT_SOURCES``
    Provenance filtering is rejection-based, not acceptance-based. The
    transcript format does carry a ground-truth ``promptSource`` field, but it
    is present on only 120 of 3,331 non-meta user entries, and the labelled and
    unlabelled sets span identical dates. Its absence is therefore not
    evidence, and an acceptance rule keyed on it discards the corpus.

``MINIMUM_CORPUS``
    A phrase used in 1 percent of prompts appears at least once in 200 prompts
    with probability ``1 - 0.99**200``, about 0.87. Below that a zero reading
    and a small non-zero reading are indistinguishable, so the CLI refuses to
    print a percentage and exits 3 rather than publish an uninterpretable one.

Neither store is committed and no prompt text reaches any output path; the
report carries only counts and phrases the skills tree already documents.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

# A transcript entry carrying any of these is not something a human typed.
# ``isSidechain`` and ``agentId`` mark a prompt an agent wrote for a subagent.
# ``isMeta`` marks a harness-injected turn. ``isCompactSummary`` and
# ``isVisibleInTranscriptOnly`` mark compaction bookkeeping. ``sourceToolUseID``
# marks a turn a tool produced. All four shapes carry the ``user`` role.
NON_HUMAN_ENTRY_FLAGS: Final = (
    "isSidechain",
    "agentId",
    "isMeta",
    "isCompactSummary",
    "isVisibleInTranscriptOnly",
    "sourceToolUseID",
)

# Claude Code records provenance directly when it knows it. ``typed`` is the
# only value that means a human typed the text. The field is sparse, so its
# absence is not evidence either way and is handled by the flag and prefix
# rules above and below rather than by rejecting the entry outright.
NON_HUMAN_PROMPT_SOURCES: Final = frozenset({"system", "sdk", "suggestion_accepted"})

# Text shapes the harness writes into the user role.
SYNTHETIC_TEXT_PREFIXES: Final = (
    "<",
    "[Request interrupted",
    "Caveat:",
    "This session is being continued",
)

# Below this many operator prompts the eval refuses to report a percentage.
# The threshold is set so a phrase used in one percent of prompts is more
# likely than not to appear at least once: 1 - 0.99**200 is about 0.87. Under
# that, a zero reading and a small non-zero reading are indistinguishable, and
# publishing either as a percentage would overstate what was measured.
MINIMUM_CORPUS: Final = 200


def is_operator_entry(entry: Mapping[str, object]) -> bool:
    """Return whether a transcript entry is a prompt a human actually typed.

    Provenance is judged by rejection, not acceptance, because the explicit
    ``promptSource`` field is present on only a small minority of entries and
    its absence spans the same dates as its presence. Requiring it would
    discard real prompts; ignoring it would admit machine-authored ones. So an
    entry is rejected when it carries a non-human flag, or when it declares a
    non-human ``promptSource``, and is otherwise judged on its text.
    """
    if any(entry.get(flag) for flag in NON_HUMAN_ENTRY_FLAGS):
        return False
    return entry.get("promptSource") not in NON_HUMAN_PROMPT_SOURCES


def is_operator_text(text: str) -> bool:
    """Return whether the text reads as a typed prompt rather than harness output."""
    stripped = text.strip()
    if not stripped or stripped.startswith(SYNTHETIC_TEXT_PREFIXES):
        return False
    return "<local-command" not in stripped


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
