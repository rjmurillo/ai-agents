"""Placement signals scored over a single Serena memory (issue #5391).

Split out of ``check_memory_placement.py`` so both files stay under the
project's 500-line ceiling (`.claude/rules/code-quality.md`) and so the
heuristic is testable without the CLI. Holds the thresholds, the signal
regexes, the per-file ``MemoryScore``, and the pure scoring function.

The four signals, scored over the prose text with fenced and indented code
blanked (`scripts/utils/markdown_parser.blank_code_block_lines`):

- s1 ``normative_sections``: at least ``MIN_NORMATIVE_SECTIONS`` headings or
  bold labels whose whole text names an obligation (Constraints, Guardrails,
  Workflow, Procedure, Protocol, Rules, Checklist, Entry Criteria, ...).
  Structural.
- s2 ``ordered_mandate``: at least ``MIN_ORDERED_MANDATES`` items of an
  ordered list state a mandate, i.e. an explicit numbered mandatory
  procedure. Structural.
- s3 ``modal_density``: at least ``MIN_MODAL_HITS`` uppercase RFC-2119 modals
  (MUST, MUST NOT, SHALL, NEVER, ALWAYS, REQUIRED). A bare word count, the
  weakest signal, so it can never flag a file on its own.
- s4 ``role_contract``: an agent-role contract or handoff schema. Structural,
  and worth ``ROLE_WEIGHT`` points rather than one.

A file is a candidate when its score reaches ``FLAG_THRESHOLD``. Prose that
narrates an incident with the word "must", or quotes a rule inside a fenced
block, cannot reach that bar: the quote is blanked before scoring, and the one
non-structural signal supplies at most one of the three points needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.utils.markdown_parser import blank_code_block_lines
from scripts.validation.yaml_utils import _parse_yaml_frontmatter

# Signal thresholds. Tuned against the full corpus; see the measurement quoted
# in the issue #5391 PR body.
MIN_NORMATIVE_SECTIONS = 2
MIN_ORDERED_MANDATES = 3
MIN_MODAL_HITS = 4
FLAG_THRESHOLD = 3

# ``role_contract`` counts double. A role contract or handoff schema inside a
# memory is prima facie misplacement: it is the shape of `.claude/agents/`,
# not of evidence, so it needs only one corroborating signal rather than two.
# Measured over the 1025-file corpus: the two memories that fire this signal
# score 0 on every other one, so the weight moves them from 1 to 2 and leaves
# the flagged set unchanged at one file.
ROLE_WEIGHT = 2

# Highest score any file can reach: three single-weight signals plus the
# double-weighted role contract. The baseline reader bounds recorded values
# by this.
MAX_SCORE = 3 + ROLE_WEIGHT

# A section label is only read as normative when it is short. "The Rule" and
# "Pre-PR Checklist" name an obligation; "Why the workflow failed in PR #226"
# is a narrative about one, and a narrative title is longer.
MAX_LABEL_WORDS = 5

# Nouns that make a short section label the name of an obligation rather than
# the name of a topic.
_NORMATIVE_SECTION_WORD = re.compile(
    r"\b(?:rules?|checklists?|guardrails?|constraints?|requirements?|"
    r"procedures?|protocols?|workflows?|responsibilities|criteria|steps?|"
    r"mandate|mandatory|policy|enforcement|prohibited|invariants?|"
    r"preconditions?|postconditions?|must|never|always|"
    r"definition of done)\b"
)

# Section names that shape an agent-role contract or a handoff schema (s4).
_ROLE_SECTIONS: frozenset[str] = frozenset(
    {
        "handoff",
        "handoff contract",
        "handoff protocol",
        "handoffs",
        "inputs",
        "outputs",
        "responsibilities",
        "role",
    }
)

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.+?)\s*#*\s*$")
_BOLD_LABEL = re.compile(r"^\s*\*\*(?P<text>[^*]+?)\*\*\s*:?\s*(?P<rest>.*)$")
_ORDERED_ITEM = re.compile(r"^\s*\d+[.)]\s+(?P<text>.+)$")

# RFC-2119 modals in the uppercase form the rule files use. Case matters: the
# lowercase "must" of narrative prose ("the branch must have been stale") is
# the single most common word in this corpus's evidence memories, while an
# uppercase MUST is a directive being written down.
_MODAL = re.compile(
    r"(?<![A-Za-z])(?:MUST NOT|MUST|SHALL NOT|SHALL|NEVER|ALWAYS|REQUIRED)"
    r"(?![A-Za-z])"
)

# Verbs that open a directive when they lead a list item. Paired with the
# ordered-list shape, they are the "explicit ordered mandatory procedure" the
# issue names; alone they are ordinary prose.
_IMPERATIVE_ITEM = re.compile(
    r"^\s*(?:Always|Never|Do not|Don't|Ensure|Verify|Run|Use|Check|Add|Set|"
    r"Write|Apply|Enforce|Create|Update|Follow|Fix|Read|Include|Document|"
    r"Confirm|Prefer|Avoid)\b"
)
_ROLE_SENTENCE = re.compile(
    r"(?:^|\n)\s*(?:you are (?:a|an|the)\b|your (?:role|mission|responsibilities)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MemoryScore:
    """Placement outcome for a single memory file."""

    path: str
    normative_sections: bool
    ordered_mandate: bool
    modal_density: bool
    role_contract: bool
    section_hits: int
    ordered_hits: int
    modal_hits: int
    exception: str | None

    @property
    def score(self) -> int:
        """Weighted number of signals that fired (0..5)."""
        return (
            int(self.normative_sections)
            + int(self.ordered_mandate)
            + int(self.modal_density)
            + ROLE_WEIGHT * int(self.role_contract)
        )

    @property
    def is_candidate(self) -> bool:
        """True when the file reads as normative or procedural content.

        Only ``modal_density`` is a bare word count, and it is worth one of
        the three points a flag needs, so a narrative that merely says MUST a
        lot cannot be flagged without also carrying the structure of a rule:
        normative section labels, an ordered mandatory procedure, or a role
        contract.
        """
        return self.score >= FLAG_THRESHOLD



# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _normalize_label(text: str) -> str:
    """Reduce a heading or bold label to comparable words.

    Emphasis, inline code, links, numbering, and trailing punctuation are
    stripped so ``### 2. **Entry Criteria**:`` and ``## Entry criteria``
    compare equal.
    """
    stripped = re.sub(r"^\s*\d+[.)]\s*", "", text)
    stripped = re.sub(r"[`*_]", "", stripped)
    stripped = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", stripped)
    stripped = re.sub(r"[^a-z0-9 ]+", " ", stripped.lower())
    return " ".join(stripped.split())


def _labels(text: str) -> list[str]:
    """Normalized section labels: markdown headings and standalone bold labels."""
    out: list[str] = []
    for line in text.splitlines():
        if heading := _HEADING.match(line):
            out.append(_normalize_label(heading.group("text")))
            continue
        if label := _BOLD_LABEL.match(line):
            out.append(_normalize_label(label.group("text")))
    return out


def count_normative_sections(labels: list[str]) -> int:
    """Short section labels that name an obligation rather than a topic."""
    return sum(
        1
        for label in labels
        if len(label.split()) <= MAX_LABEL_WORDS
        and _NORMATIVE_SECTION_WORD.search(label)
    )


def count_ordered_mandates(text: str) -> int:
    """Ordered-list items that state a mandate.

    An ordered list is the shape of a procedure; a modal or a leading
    directive verb inside its items is what makes the procedure mandatory
    rather than a recounted sequence of what happened.
    """
    mandates = 0
    for line in text.splitlines():
        item = _ORDERED_ITEM.match(line)
        if item is None:
            continue
        body = item.group("text")
        if _MODAL.search(body) or _IMPERATIVE_ITEM.match(body):
            mandates += 1
    return mandates


def count_modals(text: str) -> int:
    """Uppercase RFC-2119 modal occurrences across the prose."""
    return len(_MODAL.findall(text))


def has_role_contract(text: str, labels: list[str]) -> bool:
    """True when the file reads as an agent-role contract or handoff schema."""
    if _ROLE_SENTENCE.search(text):
        return True
    return any(label in _ROLE_SECTIONS for label in labels)


def placement_exception(content: str) -> str | None:
    """Rationale from a ``placement_exception`` frontmatter key, if present.

    Mirrors the discriminator's ``isolation_required`` frontmatter hatch. A
    bare ``false``/empty value is not an exception: the hatch exists to carry
    a reviewable reason, so an unexplained one does not qualify.
    """
    metadata = _parse_yaml_frontmatter(content)
    if not metadata:
        return None
    raw = metadata.get("placement_exception")
    if raw is None or raw is False:
        return None
    rationale = str(raw).strip()
    return rationale or None


def score_content(path: str, content: str) -> MemoryScore:
    """Score one memory's content. Pure function; the unit-test entry point."""
    prose = blank_code_block_lines(content)
    labels = _labels(prose)

    section_hits = count_normative_sections(labels)
    ordered_hits = count_ordered_mandates(prose)
    modal_hits = count_modals(prose)

    return MemoryScore(
        path=path,
        normative_sections=section_hits >= MIN_NORMATIVE_SECTIONS,
        ordered_mandate=ordered_hits >= MIN_ORDERED_MANDATES,
        modal_density=modal_hits >= MIN_MODAL_HITS,
        role_contract=has_role_contract(prose, labels),
        section_hits=section_hits,
        ordered_hits=ordered_hits,
        modal_hits=modal_hits,
        exception=placement_exception(content),
    )
