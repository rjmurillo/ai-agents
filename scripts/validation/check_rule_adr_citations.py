#!/usr/bin/env python3
# taste-lint: ignore file-size, scan, fence check, and fault report share one ratchet entry point.
"""Flag an instruction file that cites a missing or non-accepted ADR (issue #5200).

A rule, `AGENTS.md`, or `CLAUDE.md` says "per ADR-078" or "MUST comply with
ADR-080". Nothing checked the cited record's own status. `ADR-078` is
`proposed` and `ADR-080` is `superseded` by ADR-111, yet both are cited as
live authority. A reader who trusts the citation obeys a decision the record
does not hold; a reader who checks the status learns that status is not worth
reading.

## What is scanned

Git-tracked files only, read from disk, per
`.claude/skills/ai-agents-validation-and-qa/references/rule-ci-scripts.md` MUST 9. The
canonical sources and every shipped mirror of them, because a check that passes the source
while a stale mirror ships the violation to plugin consumers has not protected the consumer:

- every tracked `AGENTS.md` and `CLAUDE.md`, at the root and nested
- `templates/rules/*.md` (the source, per ADR-109)
- `.claude/rules/*.md`, `src/claude/rules/*.md`
- `.github/copilot-instructions.md`, the repository-wide Copilot guide, which loads
  on every Copilot request and is in no other glob
- `.github/instructions/*.instructions.md`, `src/copilot-cli/instructions/*.md`
- `templates/agents/**`: the agent templates and their `.mustache` and `.tmpl`
  sources
- the rendered Markdown agent trees: `src/claude/agents`,
  `src/copilot-cli/agents`, `src/vs-code-agents`, `src/cursor/agents`,
  `src/muse/agents`, `.github/agents`. `src/codex/agents` is TOML and is not
  read; it renders from the same templates.

A `.mustache` or `.tmpl` file is a fragment: its fences open in one file and
close in another. An unclosed fence there is counted and not failed. Masking in
a fragment can be wrong after that fence, and also before a lone fence that closes
a block a sibling partial opened. A fence marker is the same line open or close, so
one fragment cannot tell which it is: with an odd marker count, every line is code
under one reading and prose under the other. The scan keeps the first reading (pair
from the top) and does not skip such fragments, so real source-only prose is read;
the rendered trees, which are whole documents, are the complete read of the same
prose.

## Status resolution

Reuses :func:`check_skill_adr_bindings.adr_statuses`, which reads the
frontmatter `status:` through `check_adr_lifecycle.collect_records`, so ADR
parsing keeps one owner. Every `ADR-NNN-*.md` record carries a frontmatter
status since ADR-073 landed, so no prose fallback is needed. A record whose
status is empty (missing, unparseable, or non-scalar) is counted, not failed: it
is not `accepted`, so its citations are not skipped as if it were (issue #6506).

`proposed`, `rejected`, `deprecated` and `superseded` are non-accepted. The
issue names the first, second and fourth; `deprecated` is in ADR-073's enum and
a rule cannot cite a deprecated record as live any more than a superseded one.

## Existence

A cited number with no tracked `ADR-NNN-*.md` record is MISSING and fails,
whatever the sentence says. The link gate (`check_adr_links.py`) resolves
Markdown link targets only, so a bare `ADR-999` in prose reached no gate. An
example number that names no record belongs in a code span, which is masked.
A heading such as `## Pin policy (ADR-999)` gets the existence check and nothing
more: a heading is not prose that binds, so a heading that names a non-accepted
record is not classified.

## Citation classes

Each mention of a non-accepted ADR is placed in exactly one class. Only BINDING
fails the gate (MISSING, above, is decided before classification). A check that
guesses on ambiguous prose trains people to add ignore comments, so a mention
the classifier cannot place is UNCLASSIFIED and is reported, never failed.

- NOT A CITATION, never seen: inside an inline code span, a fenced block (its
  fence lines may be indented, as under a list item), an HTML comment or YAML
  frontmatter, or part of a file name or path such as `ADR-085-slug.md:428-431`.
- META: under a `References` style heading, after a `References:` label,
  or in a lineage clause: "ADR-092, which supersedes ADR-079" (ADR-079 is
  history), "ADR-002, formerly cited here, is deprecated", "superseded by
  ADR-111". The same sentence can hold one binding and one historical
  citation, so the test is on the mention, not the sentence.
- BINDING: the sentence carries MUST, SHALL, REQUIRED, "binding", "governs" or
  "requires", or the mention directly follows "per", "under", "comply with",
  "conform to", "governed by", "required by", "mandated by", "defined by" or
  "according to", or a compliance verb: "pass", "satisfy", "meet", "need" or
  "obey", as in "Pin changes pass ADR-080". A negator or a "once" or "first" in
  the three words before the verb ("no longer pass", "Nobody needs", "On the
  first pass") makes it history or narration, not compliance. "follows" is not a
  compliance verb: "ADR-111 follows ADR-080" is sequence, not obedience. A
  sentence or pipe cell that is only a label and ADR numbers, such as the terse
  `pins: ADR-080` that sat in `AGENTS.md`, is a pointer to the owning record and
  is BINDING too, unless the label is a history or bibliography word ("Refs:",
  "Replaces:", "Background:", "Prior art:"). A `Refs:` style label opens its own pipe
  cell only: `Refs: ADR-042 | pins: ADR-080` holds one bibliography cell and one
  binding pointer. A bibliography heading scopes the whole section.
  A compliance verb covers a coordinated list: "pass ADR-042 and ADR-080" reads
  ADR-080 through the same verb and the same negation window as ADR-042.

  The pointer default is binding-unless-history, not an allowlist of binding
  labels. Terse pipe guides such as `AGENTS.md` use arbitrary labels (`pins:`),
  and an allowlist would have missed the regression this gate exists for. The
  escape for a false positive is a history label, a code span, or a baseline
  entry.
- UNCLASSIFIED: everything else, such as "(ADR-065)" after a claim, or an
  example like "architecture violates ADR-007". Recall is partial by design.

## Not covered

A rule that restates an ADR's decision in prose without naming the ADR, as
`universal.md` MUST-4 does for ADR-093, has no citation to resolve. This check
cannot see it. Naming the ADR in that rule is an owner decision, not a
validator change.

## Ratchet

Violations exist when this gate lands, so a hard gate would red every push. The
baseline lists known violations by identity, `<path>::ADR-NNN`, not by count
(`ci-scripts.md` MUST 15 diffs on `(file, rule)` for the same reason: with a
count, one new violation hides behind one fix). A violation absent from the
baseline fails. A baseline entry the tree no longer produces also fails, so the
list shrinks when a citation is repaired and cannot mask a re-introduction.
Edit the baseline by hand: delete a line when its citation is fixed. Adding a
line legalises a violation and shows in review as an added line.

The baseline holds BINDING violations only. A MISSING record has the same key
shape, so a baseline entry could otherwise cover it after the record is deleted.
A missing record is always new, and a baseline entry that the tree no longer
produces as BINDING is stale, whatever the tree produces in its place.

A scan that cannot see every tracked file does not pass. A tracked file that is
not a regular file, or resolves outside the repository (including a symlink that
leaves it), is listed on stderr and fails the run with exit 2. A fenced block with
no closing fence masks every later line of its file, so it is listed and fails the
run with exit 1 (issue #6506), except in a fragment (see What is scanned).

Exit codes follow ADR-035: 0 ok, 1 new or stale violation or an unterminated
fence, 2 configuration fault or a tracked file the scan skipped, 3 git could not
list tracked files. Every terminal line carries the
examined count (`ci-scripts.md` MUST 12).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_REPO_ROOT = _SCRIPT_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from check_skill_adr_bindings import adr_statuses  # noqa: E402

from scripts.ci.count_ratchet import tracked_files  # noqa: E402
from scripts.hook_utilities.frontmatter_block import split_frontmatter  # noqa: E402

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

CHECK = "rule-adr-citation"
ADR_DIR = ".project-toolkit/architecture"
ADR_RECORD_GLOB = f"{ADR_DIR}/ADR-*.md"

#: ADR-073 status enum minus `accepted`. See the module docstring.
NON_ACCEPTED = frozenset({"proposed", "rejected", "deprecated", "superseded"})

SCAN_GLOBS = (
    "AGENTS.md",
    "CLAUDE.md",
    "**/AGENTS.md",
    "**/CLAUDE.md",
    "templates/rules/*.md",
    ".claude/rules/*.md",
    "src/claude/rules/*.md",
    ".github/copilot-instructions.md",
    ".github/instructions/*.instructions.md",
    "src/copilot-cli/instructions/*.md",
    "templates/agents/**",
    "src/claude/agents/*.md",
    "src/copilot-cli/agents/*.md",
    "src/vs-code-agents/*.md",
    "src/cursor/agents/*.md",
    "src/muse/agents/*.md",
    ".github/agents/*.md",
)

#: Template sources that render into a whole document only when combined.
FRAGMENT_SUFFIXES = (".mustache", ".tmpl")

_RECORD_NAME_RE = re.compile(r"(?:^|/)ADR-(\d{1,4})(?:-[^/]*)?\.md$")

BINDING = "binding"
META = "meta"
MISSING = "missing"
UNCLASSIFIED = "unclassified"

_BASELINE_PATH = Path(__file__).with_name("rule_adr_citations_baseline.json")

#: An ADR id not preceded by a path separator or word character and not followed
#: by a slug that ends in `.md`, so a file name with a line range is not a mention.
_MENTION_RE = re.compile(r"(?<![/\w-])ADR-(\d{1,4})\b(?![-\w]*\.md)")

#: A fence may be indented: a list item holds its fenced example at the item's content
#: column (`1. ` adds three spaces, a nested item more), so the open and close lines
#: allow leading blanks. A line with other text before the backticks is not a fence.
#: A fence that opens at column zero closes at column zero only, so an indented
#: marker inside it stays code. An indented fence closes at any indent.
_FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]+)?(?P<mark>```|~~~)[^\n]*\n"
    r".*?(?:^(?(indent)[ \t]*|)(?P<close>(?P=mark))[^\n]*$|\Z)",
    re.DOTALL | re.MULTILINE,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)[^\n]*?(?<!`)\1(?!`)")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_BIB_HEADING_RE = re.compile(
    r"^(?:references?|see also|sources?|bibliography|further reading|related\b.*|prior art)",
    re.IGNORECASE,
)
#: Words that open a bibliography label. Shared by `_BIB_LABEL_RE` and
#: `_POINTER_HISTORY_RE` so a label one accepts is never read as a pointer by the other.
_BIB_WORDS = r"references?|refs?|see also|sources?"
_BIB_LABEL_RE = re.compile(
    rf"^[\s>*_\-]*(?:\d+[.)]\s*)?[*_]*(?:{_BIB_WORDS})[*_]*\s*[:\-]",
    re.IGNORECASE,
)
_BLOCK_START_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\||>)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\s*\|\s*|;\s+")

_LINEAGE_WORD = r"(?:supersed\w*|replac\w*|retir\w*|obsolet\w*|deprecat\w*|formerly|previously)"
_LINEAGE_BEFORE_RE = re.compile(
    rf"\b{_LINEAGE_WORD}\s+(?:by\s+)?(?:(?:the|older|prior|earlier|former|old)\s+)?"
    r"(?:ADR-\d+(?:'s)?\s*(?:,|and|or|/)\s*)*$",
    re.IGNORECASE,
)
_LINEAGE_AFTER_RE = re.compile(
    r"^(?:'s)?\W{0,3}(?:\w+\W+){0,2}?(?:is|was|were|are|been|now)?\W*"
    r"(?:formerly|superseded|deprecated|retired|replaced|obsolete|obsoleted|withdrawn)\b",
    re.IGNORECASE,
)
_BINDING_SENTENCE_RE = re.compile(
    r"\b(?:MUST|SHALL|REQUIRED)\b|\b(?:binding|governs|requires)\b",
)
_BINDING_BEFORE_RE = re.compile(
    r"\b(?:per|under|comply with|complies with|conforms? to|governed by|required by|"
    r"mandated by|defined by|according to)\s+(?:the\s+)?(?:ADR-\d+(?:,|\s+and|\s*/)\s*)*$",
    re.IGNORECASE,
)
# A compliance verb directly before the mention: "Pin changes pass ADR-080",
# "needs an ADR-080 sidecar entry". Kept apart from `_BINDING_BEFORE_RE`, which
# check_adr_supersession_citations.py imports for ADR bodies.
_COMPLY_BEFORE_RE = re.compile(
    r"\b(?:pass(?:es)?|satisf(?:y|ies)|meets?|needs?|obeys?)\s+(?:an?\s+|the\s+)?$",
    re.IGNORECASE,
)
# A negator, "once" or "first" in the words before a compliance verb turns it into
# history or narration: "no longer pass", "Nobody needs", "On the first pass".
_COMPLY_NEGATED_RE = re.compile(
    r"\b(?:no longer|not|never|nobody|once|first)\b|n['’]t\b",
    re.IGNORECASE,
)
_COMPLY_NEGATION_WINDOW = 3
# One earlier item of a coordinated list that ends `before`: "pass ADR-042 and ADR-080"
# reads ADR-042 and the joiner off ADR-080's prefix so the verb ends it. The item is
# matched at the end only and one at a time, inside a short tail window, and at most
# `_COMPLY_LIST_MAX` times, so a long run costs a bounded amount per mention. A list
# longer than the cap, or an item wider than the window, ends the list there.
_COMPLY_LIST_MAX = 64
_COMPLY_LIST_WINDOW = 64
_COMPLY_LIST_ITEM_RE = re.compile(
    r"ADR-\d+\s*(?:,\s*(?:and|or)\b|,|\band\b|\bor\b|/|\+)(?:\s+(?:an?|the)\b)?\s*$",
    re.IGNORECASE,
)
# A sentence or pipe cell that is only `label: ADR-NNN[, ADR-MMM]`. The tail is one
# optional period and one whitespace run, so a long blanked-code-span run cannot
# backtrack through two adjacent `\s*` groups.
_POINTER_RE = re.compile(
    r"^\s*(?:[-*+>]\s+|\d+[.)]\s+)?(?P<label>[A-Za-z*_][\w */+-]{0,40}?)[*_]*:[*_]*\s*"
    r"ADR-\d+(?:\s*(?:,|and\b|/|\+)\s*ADR-\d+)*(?:\s*\.)?\s*$"
)
_POINTER_HISTORY_RE = re.compile(
    rf"{_LINEAGE_WORD}|\b(?:{_BIB_WORDS}|related|see|history|historical|was|cf|examples?|"
    r"background|context|prior(?: art)?|predecessors?|old|origins?|compare|rationale|notes?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Citation:
    """One mention of a missing or non-accepted ADR, placed in a class."""

    path: str
    line: int
    adr: int
    status: str
    """The record's frontmatter status. Equals ``kind`` for a MISSING citation, which has none."""
    kind: str
    sentence: str

    @property
    def key(self) -> str:
        return f"{self.path}::ADR-{self.adr:03d}"

    def render(self) -> str:
        if self.kind == MISSING:
            return (
                f"{self.path}:{self.line}: [{CHECK}] ADR-{self.adr:03d} has no tracked "
                f"record under {ADR_DIR}: ...{self.sentence}..."
            )
        return (
            f"{self.path}:{self.line}: [{CHECK}] ADR-{self.adr:03d} is "
            f"{self.status} but is cited as binding: ...{self.sentence}..."
        )


def unterminated_fence_line(text: str) -> int | None:
    """Line number of the first fence that never closes, or ``None``.

    ``_FENCE_RE`` lets an open fence run to the end of the file so a missing
    close does not crash the scan, but then every later citation is masked.
    Frontmatter is blanked first so a ``---`` block cannot hold a fence.
    """
    body = _blank_frontmatter(text)
    for match in _FENCE_RE.finditer(body):
        if match.group("close") is None:
            return body.count("\n", 0, match.start()) + 1
    return None


def _blank(match: re.Match[str]) -> str:
    """Replace a match with spaces, keeping newlines so line numbers hold."""
    return _blank_text(match.group(0))


def _blank_text(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _blank_frontmatter(text: str) -> str:
    """Blank the leading frontmatter block, found by ``frontmatter_block.py``.

    Offsets and line numbers hold. The block runs through the closing fence line
    and any blank lines after it, which hold no citation either.
    """
    split = split_frontmatter(text)
    if not split.found:
        return text
    return _blank_text(text[: split.body_start]) + split.body


def mask_noise(text: str) -> str:
    """Blank out text that cannot hold a citation, preserving every offset."""
    text = _blank_frontmatter(text)
    for pattern in (_FENCE_RE, _COMMENT_RE, _CODE_SPAN_RE):
        text = pattern.sub(_blank, text)
    return text


def _is_bibliography_heading(title: str) -> bool:
    return bool(_BIB_HEADING_RE.match(title.strip("*_ ")))


def _continues(previous: str, line: str) -> bool:
    """True when ``line`` continues the sentence ``previous`` left open.

    Conservative on purpose: a wrap that starts a capital or ends in terminal
    punctuation starts a new block. A split can only turn a BINDING mention into
    UNCLASSIFIED, never the reverse.
    """
    stripped = line.strip()
    if not stripped or _BLOCK_START_RE.match(line) or stripped[0].isupper() or stripped[0] in "*#":
        return False
    return bool(previous.strip()) and previous.rstrip()[-1] not in ".!?:|"


def _blocks(masked: str) -> list[tuple[bool, list[tuple[int, str]]]]:
    """Split text into blocks of ``(lineno, text)`` lines, tagged by heading scope.

    The tag is the bibliography heading scope only. An inline label such as
    `Refs:` is read per cell by :func:`_mentions_in_block`, so it cannot spill into
    the next cell of a pipe row.
    """
    blocks: list[tuple[bool, list[tuple[int, str]]]] = []
    bib_level = 0
    current: list[tuple[int, str]] = []
    for number, line in enumerate(masked.split("\n"), start=1):
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if bib_level and level <= bib_level:
                bib_level = 0
            if not bib_level and _is_bibliography_heading(heading.group(2)):
                bib_level = level
            current = []
            continue
        if not line.strip():
            current = []
            continue
        if current and _continues(current[-1][1], line):
            current.append((number, line))
            continue
        current = [(number, line)]
        blocks.append((bool(bib_level), current))
    return blocks


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_SPLIT_RE.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return spans


def _complies(before: str) -> bool:
    """True when ``before`` ends in a compliance verb that nothing negates.

    Earlier items of a coordinated ADR list are stripped first, so every item reads
    the same verb and the same negation window. Only ADR items are stripped: any
    other word between the verb and the mention still ends the match.
    """
    end = len(before)
    for _ in range(_COMPLY_LIST_MAX):
        item = _COMPLY_LIST_ITEM_RE.search(before, max(0, end - _COMPLY_LIST_WINDOW), end)
        if item is None:
            break
        end = item.start()
    before = before[:end]
    verb = _COMPLY_BEFORE_RE.search(before)
    if verb is None:
        return False
    lead = " ".join(before[: verb.start()].split()[-_COMPLY_NEGATION_WINDOW:])
    return _COMPLY_NEGATED_RE.search(lead) is None


def is_binding_pointer(sentence: str) -> bool:
    """True when ``sentence`` is only a non-history label and ADR numbers."""
    pointer = _POINTER_RE.match(sentence)
    return pointer is not None and _POINTER_HISTORY_RE.search(pointer.group("label")) is None


def classify(
    sentence: str,
    match: re.Match[str],
    tail_end: int,
    in_bibliography: bool,
    pointer: bool | None = None,
) -> str:
    """Class of the mention ``match`` found in ``sentence``.

    ``tail_end`` bounds the text after the mention at the next ADR mention, so
    "ADR-092, which supersedes ADR-079" reads ADR-092's tail as ", which
    supersedes" and not as a statement that ADR-092 is retired. ``pointer`` is
    :func:`is_binding_pointer` for ``sentence``; a caller that classifies many
    mentions of one sentence computes it once and passes it in.
    """
    if in_bibliography:
        return META
    before = sentence[: match.start()]
    after = sentence[match.end() : tail_end]
    if _LINEAGE_BEFORE_RE.search(before) or _LINEAGE_AFTER_RE.match(after):
        return META
    if _BINDING_SENTENCE_RE.search(sentence) or _BINDING_BEFORE_RE.search(before):
        return BINDING
    if _complies(before):
        return BINDING
    if pointer is None:
        pointer = is_binding_pointer(sentence)
    return BINDING if pointer else UNCLASSIFIED


def _mentions_in_sentence(
    path: str,
    sentence: str,
    line_of: Callable[[int], int],
    in_bibliography: bool,
    statuses: dict[int, str],
    unknown: set[int],
    records: frozenset[int] | None,
) -> list[Citation]:
    """Citations of one sentence. ``line_of`` maps a sentence offset to a line number."""
    matches = list(_MENTION_RE.finditer(sentence))
    pointer = is_binding_pointer(sentence) if matches else False
    found: list[Citation] = []
    for index, match in enumerate(matches):
        adr = int(match.group(1))
        status = statuses.get(adr)
        lineno = line_of(match.start())
        if records is not None and adr not in records:
            found.append(Citation(path, lineno, adr, MISSING, MISSING, sentence))
            continue
        if not status:
            unknown.add(adr)
            continue
        if status not in NON_ACCEPTED:
            continue
        tail_end = matches[index + 1].start() if index + 1 < len(matches) else len(sentence)
        kind = classify(sentence, match, tail_end, in_bibliography, pointer)
        found.append(Citation(path, lineno, adr, status, kind, sentence))
    return found


def _mentions_in_block(
    path: str,
    block: list[tuple[int, str]],
    in_bibliography: bool,
    statuses: dict[int, str],
    unknown: set[int],
    records: frozenset[int] | None = None,
) -> list[Citation]:
    text = " ".join(line for _, line in block)
    starts: list[tuple[int, int]] = []
    offset = 0
    for number, line in block:
        starts.append((offset, number))
        offset += len(line) + 1
    found: list[Citation] = []
    for start, end in _sentence_spans(text):

        def line_of(relative: int, start: int = start) -> int:
            return max(n for o, n in starts if o <= start + relative)

        # A label opens the cell it starts: the text from the last pipe before this
        # sentence. A block with no pipe has one cell, the whole block.
        cell = text[text.rfind("|", 0, start) + 1 :]
        sentence_bibliography = in_bibliography or bool(_BIB_LABEL_RE.match(cell))
        found.extend(
            _mentions_in_sentence(
                path, text[start:end], line_of, sentence_bibliography, statuses, unknown, records
            )
        )
    return found


def _heading_missing(path: str, masked: str, records: frozenset[int]) -> list[Citation]:
    """MISSING citations in heading lines, which `_blocks` skips.

    Existence only: a heading is not prose that binds, so a heading that names a
    non-accepted record is not classified.
    """
    found: list[Citation] = []
    for number, line in enumerate(masked.split("\n"), start=1):
        if not _HEADING_RE.match(line):
            continue
        for match in _MENTION_RE.finditer(line):
            adr = int(match.group(1))
            if adr not in records:
                found.append(Citation(path, number, adr, MISSING, MISSING, line))
    return found


def _excerpt(line: str, adr: int, width: int = 60) -> str:
    """The author's own text around the first mention of ``adr`` on ``line``."""
    match = re.search(rf"ADR-0*{adr}\b", line)
    centre = match.start() if match else 0
    return line[max(0, centre - width) : centre + width].strip()


def citations_in(
    path: str,
    text: str,
    statuses: dict[int, str],
    unknown: set[int],
    records: frozenset[int] | None = None,
) -> list[Citation]:
    """Every mention of a missing or non-accepted ADR in ``text``, classified.

    ``records`` is the set of ADR numbers that have a tracked record. A mention
    outside it is MISSING. ``None`` skips the existence check, for a caller that
    holds statuses only.
    """
    found: list[Citation] = []
    masked = mask_noise(text)
    if records is not None:
        found.extend(_heading_missing(path, masked, records))
    for in_bibliography, block in _blocks(masked):
        found.extend(_mentions_in_block(path, block, in_bibliography, statuses, unknown, records))
    # The masked sentence is blanked where code spans were, which reads badly in
    # a report. Show the author's own line instead.
    lines = text.split("\n")
    return [replace(c, sentence=_excerpt(lines[c.line - 1], c.adr)) for c in found]


@dataclass(frozen=True, slots=True)
class ScanResult:
    citations: list[Citation]
    candidates: int
    examined: int
    absent: list[str]
    unknown: set[int]
    unterminated: list[str] = field(default_factory=list)
    fragments: list[str] = field(default_factory=list)

    @property
    def binding(self) -> list[Citation]:
        return [c for c in self.citations if c.kind == BINDING]

    @property
    def missing(self) -> list[Citation]:
        return [c for c in self.citations if c.kind == MISSING]

    @property
    def failing(self) -> list[Citation]:
        """Citations the ratchet holds: BINDING and MISSING."""
        return [c for c in self.citations if c.kind in (BINDING, MISSING)]

    @property
    def unclassified(self) -> list[Citation]:
        return [c for c in self.citations if c.kind == UNCLASSIFIED]


def _readable(repo_root: Path, rel: str) -> Path | None:
    """The tracked file's path when it is a regular file inside the repository."""
    path = repo_root / rel
    try:
        inside = path.resolve().is_relative_to(repo_root.resolve())
    except OSError:
        return None
    return path if inside and path.is_file() else None


def adr_record_numbers(repo_root: Path) -> frozenset[int] | None:
    """ADR numbers that have a tracked record, or ``None`` when git cannot list them.

    Read from the index, not from parsed statuses: a record whose frontmatter did
    not parse is absent from ``adr_statuses`` and still exists.
    """
    relatives = tracked_files(repo_root, (ADR_RECORD_GLOB,))
    if relatives is None:
        return None
    numbers = (_RECORD_NAME_RE.search(rel) for rel in relatives)
    return frozenset(int(match.group(1)) for match in numbers if match)


def scan(repo_root: Path, statuses: dict[int, str]) -> ScanResult | str:
    """Classify every missing or non-accepted citation in the tracked scan set.

    Returns the fault reason when git could not list the files, so a gate that
    enumerated nothing never reports an empty findings list as a clean tree.
    """
    listed = tracked_files(repo_root, SCAN_GLOBS)
    if listed is None:
        return (
            f"git could not list tracked rule files under {repo_root}, so nothing "
            "was examined and the gate did not run"
        )
    records = adr_record_numbers(repo_root)
    if records is None:
        return (
            f"git could not list ADR records under {ADR_DIR} in {repo_root}, so nothing "
            "was examined and the gate did not run"
        )
    relatives = sorted(set(listed))
    citations: list[Citation] = []
    absent: list[str] = []
    unterminated: list[str] = []
    fragments: list[str] = []
    unknown: set[int] = set()
    for rel in relatives:
        path = _readable(repo_root, rel)
        if path is None:
            absent.append(rel)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fence_line = unterminated_fence_line(text)
        if fence_line is not None:
            holder = fragments if rel.endswith(FRAGMENT_SUFFIXES) else unterminated
            holder.append(f"{rel}:{fence_line}")
        citations.extend(citations_in(rel, text, statuses, unknown, records))
    return ScanResult(
        citations,
        len(relatives),
        len(relatives) - len(absent),
        absent,
        unknown,
        unterminated,
        fragments,
    )


def read_baseline(path: Path) -> set[str] | str:
    """Known-violation keys, or a one-line reason the file cannot be used."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return f"baseline {path} could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return f"baseline {path} is not valid JSON: {exc}"
    known = payload.get("known") if isinstance(payload, dict) else None
    if not isinstance(known, list) or not all(isinstance(item, str) for item in known):
        return f"baseline {path} has no `known` list of strings"
    return set(known)


def _config_fault(adr_dir: Path, statuses: dict[int, str]) -> str | None:
    if not adr_dir.is_dir():
        return f"ADR directory {adr_dir} does not exist, so no status could be resolved"
    if not statuses:
        return f"no ADR records found under {adr_dir}, so every citation would resolve to nothing"
    return None


def _report(result: ScanResult, new: list[str], stale: list[str], verbose: bool) -> None:
    for citation in result.failing:
        if citation.key in new:
            print(citation.render())
    for key in stale:
        print(
            f"{key}: [{CHECK}] baseline entry no longer produced by the tree. "
            "Delete the line from the baseline."
        )
    if verbose:
        for citation in result.unclassified:
            print(f"{citation.path}:{citation.line}: [{CHECK}] unclassified ADR-{citation.adr:03d}")


def _report_fences(result: ScanResult, verbose: bool) -> None:
    for location in result.unterminated:
        print(
            f"{location}: [{CHECK}] code fence is never closed, so every later line of "
            "the file is masked and its citations went unchecked.",
            file=sys.stderr,
        )
    if not verbose:
        return
    for location in result.fragments:
        print(
            f"{location}: [{CHECK}] code fence is never closed in a template fragment, "
            "so later lines of the fragment are masked; counted, not failed.",
            file=sys.stderr,
        )


def _scope_line(result: ScanResult, current: set[str], baseline: set[str]) -> str:
    """Counts for the terminal line. ``known`` counts baselined BINDING keys only.

    The total is the combined failing keys. A MISSING record is never known: the
    baseline holds binding violations alone.
    """
    binding_keys = {c.key for c in result.binding}
    binding = len(binding_keys)
    missing = len({c.key for c in result.missing})
    return (
        f"{binding} binding violation(s) and {missing} missing record(s), "
        f"{len(current)} failing ({len(binding_keys & baseline)} known), "
        f"{len(result.unclassified)} unclassified, across "
        f"{result.examined} of {result.candidates} tracked instruction file(s), "
        f"{len(result.unknown)} ADR number(s) with no usable status, "
        f"{len(result.fragments)} fragment fence(s) not failed"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Flag an instruction file citing a missing or non-accepted ADR (issue #5200)."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root to scan.")
    parser.add_argument("--baseline", default=str(_BASELINE_PATH), help="Known-violation list.")
    parser.add_argument("--verbose", action="store_true", help="List unclassified mentions.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    adr_dir = repo_root / ADR_DIR
    statuses = adr_statuses(repo_root, adr_dir) if adr_dir.is_dir() else {}
    fault = _config_fault(adr_dir, statuses)
    baseline = read_baseline(Path(args.baseline)) if fault is None else fault
    if isinstance(baseline, str):
        print(f"[{CHECK}] config: {baseline}", file=sys.stderr)
        return EXIT_CONFIG

    result = scan(repo_root, statuses)
    if isinstance(result, str):
        print(f"[{CHECK}] external: {result}", file=sys.stderr)
        return EXIT_EXTERNAL
    if not result.examined:
        print(
            f"[{CHECK}] config: examined 0 of {result.candidates} tracked instruction file(s), "
            "so this run measured nothing",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    if result.absent:
        for rel in result.absent:
            print(
                f"{rel}: [{CHECK}] tracked file is not a regular file inside the repository, "
                "so it was not scanned",
                file=sys.stderr,
            )
        print(
            f"[{CHECK}] config: skipped {len(result.absent)} of {result.candidates} "
            "tracked instruction file(s); a gate that cannot see every file has not passed.",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    # A MISSING key is `<path>::ADR-NNN`, the same shape as a BINDING key. If the
    # baseline could cover it, deleting a baselined record would turn that entry
    # into a pass. So the baseline is matched against BINDING keys only: a missing
    # record is always new, and a baseline entry for it is stale.
    current = {c.key for c in result.failing}
    binding_keys = {c.key for c in result.binding}
    new = sorted((binding_keys - baseline) | {c.key for c in result.missing})
    stale = sorted(baseline - binding_keys)
    _report(result, new, stale, args.verbose)
    _report_fences(result, args.verbose)
    scope = _scope_line(result, current, baseline)
    if new or stale or result.unterminated:
        print(
            f"[{CHECK}] REGRESSION: {len(new)} new, {len(stale)} stale, "
            f"{len(result.unterminated)} unterminated fence(s); {scope}.",
            file=sys.stderr,
        )
        return EXIT_REGRESSION
    print(f"[{CHECK}] at baseline: {scope}.")
    return EXIT_OK


def validate_rule_adr_citations(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True only when the run completed with no new or stale entry.

    A configuration fault (exit 2) and an external fault (exit 3) return False.
    A gate that could not run has not passed.
    """
    return main(["--repo-root", str(repo_root)]) == EXIT_OK


# Public names for check_adr_supersession_citations.py, which parses ADR prose
# with this gate's masking, block, sentence, mention and lineage rules.
BINDING_BEFORE_RE = _BINDING_BEFORE_RE
BLOCK_START_RE = _BLOCK_START_RE
CODE_SPAN_RE = _CODE_SPAN_RE
COMMENT_RE = _COMMENT_RE
FENCE_RE = _FENCE_RE
HEADING_RE = _HEADING_RE
LINEAGE_AFTER_RE = _LINEAGE_AFTER_RE
LINEAGE_BEFORE_RE = _LINEAGE_BEFORE_RE
MENTION_RE = _MENTION_RE
blank = _blank
readable = _readable
sentence_spans = _sentence_spans


if __name__ == "__main__":
    sys.exit(main())
