#!/usr/bin/env python3
# taste-lint: ignore file-size. A large share of the lines are comments and
# docstrings, most of them the verbatim ADR-073 and check_adr_uniqueness.py
# quotes .claude/rules/canonical-source-mirror.md requires. Logic alone is
# well under the ceiling, so a split would move prose between files rather
# than reduce anything. (Deliberately no exact line count here: an earlier
# version cited "192 of the 558 lines" and it went stale on the very next
# edit that added lines without updating the count, Copilot, PR #5209
# round-10 review.)
"""Generate .agents/architecture/README.md, a current-state index of the ADR corpus.

`AGENTS.md` points every agent at `.agents/architecture/ADR-*.md`. That is 98
records, so "which decisions bind me right now" gets answered by grepping a
keyword and trusting the first hit. A superseded PowerShell mandate and an
accepted Python mandate look identical to that reader.

This is the consumer ADR-073 gated its deferred phases on. Its "Consumer trigger
and success metric" paragraph reads verbatim:

    **Consumer trigger and success metric.** Phases 2 to 4 proceed only when at
    least one concrete consumer is built: a stale-ADR detector, a generated
    current-state index, or a dependency viewer. Success is measured by that
    consumer reading frontmatter instead of scraping prose, and by zero
    prose-vs-frontmatter drifts surviving a gate run.

So `status`, `date` and `superseded-by` are read from frontmatter and never from
the body, running for every enum value the `status` query ADR-073 gives under
"Positive Consequences". The id comes from the filename, because 10 of the 40
backfilled records carry no `id` key while the filename is always present and is
the link a reader clicks. Title, decision summary and blocking condition are
quoted from the body; the helpers below name where each comes from.

Stricter/looser/different than canonical
----------------------------------------

ADR-073's example uses `python-frontmatter`; this module uses `yaml.safe_load` on
a regex-delimited block, the parser its own Phase 3 mandates ("Flip the
`validate-adr` gate to frontmatter-parse using `yaml.safe_load`") and the one
`build/generate_agent_catalog.py` already uses. Same contract, no new dependency.

Stricter on one point: ADR-073 says queries "tolerate missing fields (default to
`proposed`)". This index refuses to, because a defaulted status printed in a
current-state index is indistinguishable from a recorded one. Records with no
frontmatter land under **Needs backfill** with no status at all. Malformed
frontmatter, and a `status` outside the enum, fail the run and name the file:
silent omission is worse, because a reader who cannot find ADR-044 here concludes
it does not exist and cites something else.

No banner, no timestamp, no "do not edit" header (`.claude/rules/universal.md`
MUST-NOT-6). Staleness is caught by `build_all.py --check`, which
`scripts/validation/check_generated_staleness.py` runs, not by a header.

EXIT CODES (ADR-035):
  0  - Success (or --check passed with no drift)
  1  - Logic error (--check drift; malformed, non-mapping, out-of-enum, or
       title-less record)
  2  - Configuration error (ADR directory missing)
  3  - External error (an ADR file could not be read or decoded)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent

# Frontmatter delimiter. Mirrors build/generate_agent_catalog.py:
#   _FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")
# Quoted verbatim per .claude/rules/canonical-source-mirror.md: capture the YAML
# block between the leading and second ``---`` fence, then the body.
_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")

# ADR-NNN-<slug>.md. Mirrors scripts/validation/check_adr_uniqueness.py:38:
#   ADR_FILENAME_RE = re.compile(r"^ADR-(\d{2,})-[^/]+\.md$")
# Quoted verbatim. Reusing the uniqueness gate's pattern is what excludes
# ADR-TEMPLATE.md, which the glob matches and whose id is the literal ADR-NNN.
_ADR_FILENAME_RE = re.compile(r"^ADR-(\d{2,})-[^/]+\.md$")

# An id reference inside frontmatter: "ADR-091", "adr-91", or a bare integer
# rendered as a string by _scalar() below. Mirrors
# scripts/validation/check_adr_lifecycle.py:132-133 verbatim:
#   # An id reference inside frontmatter: "ADR-091", "adr-91", or a bare integer.
#   _ADR_REFERENCE_RE = re.compile(r"^ADR[-_ ]?(\d{1,4})$", re.IGNORECASE)
# The lifecycle gate is the schema's canonical reference parser (ADR-073 names
# it as such); a `superseded-by` value that gate accepts as a valid reference
# must resolve to the same record here, or a record can pass lifecycle
# validation while the index silently fails to find its successor and prints
# the raw, unlinked reference instead (Copilot, PR #5209).
_ADR_REFERENCE_RE = re.compile(r"^ADR[-_ ]?(\d{1,4})$", re.IGNORECASE)

_ADR_GLOB = "ADR-*.md"
_ADR_DIR_RELATIVE = Path(".agents") / "architecture"
_OUTPUT_RELATIVE = _ADR_DIR_RELATIVE / "README.md"

# The ADR-073 enum, verbatim from its Decision section:
#   status: proposed | accepted | rejected | deprecated | superseded   # enum, no prose
_STATUS_ENUM = ("proposed", "accepted", "rejected", "deprecated", "superseded")

# Two terminal states, one table: a reader arriving from a stale citation needs
# the same redirect either way.
_RETIRED_STATUSES = ("superseded", "deprecated")

_H1_RE = re.compile(r"(?m)^#[ \t]+(.+?)[ \t]*$")

# "ADR-073: Machine-Readable ..." -> "Machine-Readable ...". The id has its own
# column.
_TITLE_ID_PREFIX_RE = re.compile(r"^ADR-\d+\s*[:.-]?\s*", re.IGNORECASE)

# ``## Decision`` or ``## Decision Outcome`` exactly, so the MADR heading
# ``## Decision Drivers`` does not match.
_DECISION_HEADING_RE = re.compile(r"(?m)^##[ \t]+Decision(?:[ \t]+Outcome)?[ \t]*$")
_STATUS_HEADING_RE = re.compile(r"(?m)^##[ \t]+Status[ \t]*$")

# A section runs to the next level-1 or level-2 heading. Not "any heading":
# ADR-001, ADR-026 and ADR-085 open Decision with an ``###`` subsection, and
# stopping at level 3 leaves those sections empty.
_SECTION_END_RE = re.compile(r"(?m)^#{1,2}[ \t]+\S")

_FENCE_RE = re.compile(r"(?ms)^[ \t]*```.*?^[ \t]*```[ \t]*$")

# Stripped before the sentence split, not after: ADR-094 writes
# ``1. **Supersede ADR-044 in full.** Keep ...``, where the closing ``**`` sits
# between the period and the space and hides the boundary from a ``[.!?]``
# lookbehind.
_EMPHASIS_RE = re.compile(r"\*\*|__")
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)])[ \t]+")

# Requiring a sentence-opening character after the space keeps "e.g. the"
# intact; requiring the whitespace keeps "ADR-086.md)" and "4.0.0" intact.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'\[(`*])')

# Dropped from the blocker cell: the section heading already carries the status.
_LEADING_PROPOSED_RE = re.compile(r"^Proposed\b[ \t]*[.:-]?[ \t]*", re.IGNORECASE)

# Table cells are one line. Longer prose is cut on a word boundary; the record
# itself is one click away.
_CELL_MAX_CHARS = 200


class AdrIndexError(Exception):
    """An ADR record could not be parsed into an index row."""


class _DuplicateKeyError(yaml.YAMLError):
    """Raised when a mapping declares the same key twice."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys.

    PyYAML resolves duplicates last-wins and reports nothing, so a record
    carrying `status: proposed` near the top and `status: accepted` lower in the
    same block parses as accepted while reading as proposed to a human scanning
    the first lines. For a lifecycle gate that is a forgery vector, not a
    formatting nit: the visible declaration and the enforced one differ.

    The repo already treats this as a governance risk. `detect_adr_changes.py`
    carries `_has_duplicate_keys` with the docstring "Duplicate keys are
    malformed YAML and can hide a governance change (a second ``status:``
    line masking the first)", and fails its frontmatter-only exemption closed
    on them. Both readers detect at the parser now, not by scanning lines: an
    earlier revision of `_has_duplicate_keys` (then named
    `_has_duplicate_top_level_keys`) matched only `^[A-Za-z0-9_-]+:` line
    prefixes, which is a different question than YAML asks, and three of four
    quoting spellings walked through it while `yaml.safe_load` enforced one
    value for all of them (Copilot, PR #5230). Rewritten to hook the
    constructor the same way this loader does, it now agrees with this
    loader exactly: both catch duplicates nested inside a mapping value and
    are not fooled by quoting or comments, because both compare constructed
    keys rather than raw text.
    """


def _no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    """Reject a mapping that declares the same key twice.

    Keys are collected in a list and compared with ``==`` rather than kept in a
    set. A set looks like the natural choice and is wrong here, because a YAML
    key need not be hashable: ``? [a, b]`` builds a list key, and both ``in``
    and ``add`` raise ``TypeError`` on it. An earlier revision guarded only the
    membership test, with a ``# pragma: no cover - unhashable keys are not
    valid here`` comment asserting the case was unreachable. It is reachable,
    the comment was wrong, and ``seen.add(key)`` then raised the same
    ``TypeError`` one line later, escaping ``parse_frontmatter``'s
    ``yaml.YAMLError`` conversion and ``main``'s exit-code handling to produce a
    traceback instead of the documented exit 1. Copilot found it on PR #5230.

    ``==`` is defined for every constructed value, so the comparison never
    raises, and an unhashable key that is NOT duplicated falls through to
    ``construct_mapping``, which raises PyYAML's own ``ConstructorError``
    (a ``yaml.YAMLError``, verified by execution). Both paths now land inside
    the error contract.

    The list is O(n^2) against the mapping's own key count. Frontmatter blocks
    hold single-digit key counts, so this is not worth a hashable fast path
    that would reintroduce the two-code-path bug.
    """
    seen: list[Any] = []
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if any(key == earlier for earlier in seen):
            raise _DuplicateKeyError(f"duplicate key {key!r} in frontmatter mapping")
        seen.append(key)
    mapping: dict[Any, Any] = loader.construct_mapping(node, deep=True)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


@dataclass(frozen=True, slots=True)
class AdrRecord:
    """One ADR reduced to its index row. ``status`` is ``None`` for a record with
    no frontmatter block, or one whose frontmatter omits the `status` key
    entirely; both route to Needs backfill unlabelled. A `status` key present
    but null, empty, or out of the ADR-073 enum is a distinct defect and raises
    instead (see `_status_of`), rather than collapsing into the same `None`."""

    number: int
    adr_id: str
    filename: str
    title: str
    status: str | None
    date: str
    summary: str
    successor: str | None
    blocker: str
    review_by: str


# --- Parsing --------------------------------------------------------------


def parse_frontmatter(content: str, path: Path) -> tuple[dict[str, object] | None, str]:
    """Split one ADR into (frontmatter mapping, body).

    The mapping is ``None`` when there is no frontmatter block. Every other
    failure raises: a block that exists but does not parse is a defect the author
    must see, not a record to drop from the index.

    The body is returned separately because frontmatter can hold markdown-shaped
    lines. ADR-068 and ADR-085 open their block with the YAML comment
    ``# taste-lint: ignore file-size, ...``, which a whole-file H1 search reads as
    the title.

    An opened-but-unterminated block (starts with ``---``, no closing ``---``
    fence) is a distinct defect from a genuinely absent one, and
    ``_FRONTMATTER_RE`` cannot match either without the closing fence, so it
    collapses both to ``None``. Left uncorrected, that routes a record with
    malformed lifecycle metadata into Needs backfill exactly as if it had
    never carried a schema at all, silently rather than as a defect an author
    would see (PR #5209 review, discussion_r3832255493).
    """
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        if content.startswith("---"):
            raise AdrIndexError(
                f"{path.name} opens with '---' but has no closing '---' fence; "
                "the frontmatter block is unterminated"
            )
        return None, content
    body = match.group(2)
    try:
        parsed = yaml.load(match.group(1), Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise AdrIndexError(f"invalid YAML frontmatter in {path.name}: {exc}") from exc
    if parsed is None:
        return {}, body
    if not isinstance(parsed, dict):
        raise AdrIndexError(f"frontmatter in {path.name} is not a mapping")
    return parsed, body


def _status_of(frontmatter: dict[str, object], path: Path) -> str | None:
    """Return the lower-cased status enum value, or ``None`` when the key is
    absent entirely.

    An out-of-enum value raises rather than defaulting: a defaulted status
    printed in a current-state index reads exactly like a recorded one. A
    `status` key that IS present but null or empty is the same class of
    defect, not the absent-key case: the author addressed the field and left
    it broken, which is different from a record that has never been touched.
    ``frontmatter.get("status")`` cannot tell those apart (both a missing key
    and an explicit ``status: null`` return ``None``), so the presence check
    below uses ``in`` first. Previously both collapsed to the same silent
    ``None``, routing a record with partial, broken metadata into Needs
    backfill exactly as if it had no schema at all (PR #5209 review).
    """
    if "status" not in frontmatter:
        return None
    raw = frontmatter["status"]
    if raw is None:
        raise AdrIndexError(
            f"frontmatter 'status' in {path.name} is present but null; omit the "
            "key entirely if status has not been backfilled yet"
        )
    if not isinstance(raw, str):
        raise AdrIndexError(
            f"frontmatter 'status' in {path.name} must be a string, got {type(raw).__name__}"
        )
    value = raw.strip().lower()
    if not value:
        raise AdrIndexError(
            f"frontmatter 'status' in {path.name} is present but empty; omit the "
            "key entirely if status has not been backfilled yet"
        )
    if value not in _STATUS_ENUM:
        allowed = ", ".join(_STATUS_ENUM)
        raise AdrIndexError(
            f"frontmatter 'status' in {path.name} is {raw!r}; expected one of: {allowed}"
        )
    return value


def _scalar(frontmatter: dict[str, object], key: str) -> str:
    """Render a scalar frontmatter field as a stable string.

    ``yaml.safe_load`` turns an unquoted ``2026-06-19`` into a ``datetime.date``
    and a quoted one into ``str``; both normalise to the same ISO text here.
    """
    value = frontmatter.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _extract_title(body: str, path: Path) -> str:
    """Return the H1 title with any redundant ``ADR-NNN:`` prefix removed."""
    match = _H1_RE.search(body)
    if match is None:
        raise AdrIndexError(f"{path.name} has no H1 title line")
    title = _TITLE_ID_PREFIX_RE.sub("", match.group(1).strip()).strip()
    return title or match.group(1).strip()


def _section_body(body: str, heading: re.Pattern[str]) -> str:
    """Text under the first match of ``heading``, up to the next level-1 or
    level-2 heading, so ``###`` subsections stay inside their section."""
    match = heading.search(body)
    if match is None:
        return ""
    rest = body[match.end() :]
    end = _SECTION_END_RE.search(rest)
    return rest[: end.start()] if end else rest


def _first_paragraph(section: str) -> str:
    """The section's first prose paragraph as one line. Fenced code and
    subsection headings are skipped, so a Decision section opening with
    ``### 1. ...`` or a YAML block yields the prose beneath it, not nothing."""
    stripped = _FENCE_RE.sub("", section)
    for block in stripped.split("\n\n"):
        lines = [
            line
            for line in block.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not lines:
            continue
        text = " ".join(" ".join(_first_item(lines)).split())
        text = _LIST_MARKER_RE.sub("", _EMPHASIS_RE.sub("", text))
        if text:
            return text
    return ""


def _first_item(lines: list[str]) -> list[str]:
    """Narrow a list block to its first item, leaving prose blocks whole.

    ADR-044, ADR-056 and ADR-094 open Decision with a numbered list. Joining
    every item yields "Supersede ADR-044 in full. 2. Keep ..." and the sentence
    splitter cannot cut it, because a digit is not a sentence start.
    """
    if not _LIST_MARKER_RE.match(lines[0].lstrip()):
        return lines
    item = [lines[0]]
    for line in lines[1:]:
        if _LIST_MARKER_RE.match(line.lstrip()):
            break
        item.append(line)
    return item


def _decision_summary(body: str) -> str:
    """One-line decision summary, or ``""`` when the record states none.

    Covers the canonical ``## Decision`` and the MADR ``## Decision Outcome``.
    ADR-030 and ADR-095 have neither, so their rows carry the title alone.
    """
    paragraph = _first_paragraph(_section_body(body, _DECISION_HEADING_RE))
    return _SENTENCE_SPLIT_RE.split(paragraph, 1)[0].strip() if paragraph else ""


def _blocking_condition(body: str) -> str:
    """What a proposed record says is blocking its acceptance, or ``""``.

    The prose ``## Status`` paragraph minus a leading bare "Proposed" token. This
    reads a record's statement of its own blocker; it does not infer status,
    which comes from frontmatter and nowhere else.
    """
    paragraph = _first_paragraph(_section_body(body, _STATUS_HEADING_RE))
    return _LEADING_PROPOSED_RE.sub("", paragraph).strip()


def _blocker_cell(record: AdrRecord) -> str:
    """What is blocking a proposed record: its review date, its prose, or both.

    Issue #5198 specifies the Proposed table carries "the condition **or review
    date** blocking acceptance". ``review-by`` is the machine-readable half and
    the prose ``## Status`` paragraph is the human half, so a record may declare
    either, both, or neither.

    A past-due date is surfaced, not marked. This cell renders whatever
    ``review-by`` says (``review by 2026-01-01``), current or overdue,
    identically either way: there is no "(overdue)" suffix or other flag here,
    and no other gate adds one either. Detecting that a date has passed
    requires reading the wall clock, which this renderer must not do (it is
    required to be deterministic: same input, byte-identical output, and a
    clock read would make output depend on run date). ``check_adr_lifecycle.py``
    does not fill that gap: its ``CHECKS`` tuple has no rule that reads
    ``review-by`` at all, past-due or otherwise (verified: the string does not
    appear in that file). So today, nothing in this codebase flags an overdue
    ``review-by`` date; a reader has to notice one by eye. The whole reason the
    field exists (issue #5193) is that ADR-002 and ADR-039 sat seven months past
    a provisional window nobody could see, and until #5193 builds the check
    this cell's plain rendering has the same blind spot, one layer less deep:
    at least the date is visible here, where it was not visible at all before
    this field existed (Copilot, PR #5209 round-5 review).
    """
    if not record.review_by:
        return record.blocker
    stamped = f"review by {record.review_by}"
    if not record.blocker:
        return stamped
    return f"{stamped}; {record.blocker}"


def build_record(path: Path) -> AdrRecord:
    """Parse one ADR file into an index row. Raises AdrIndexError on defects."""
    match = _ADR_FILENAME_RE.match(path.name)
    if match is None:  # pragma: no cover - callers filter first
        raise AdrIndexError(f"{path.name} is not a canonical ADR-NNN-slug.md name")
    number = int(match.group(1))
    # CRLF normalised once so every regex below sees a bare newline.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    frontmatter, body = parse_frontmatter(text, path)

    status = _status_of(frontmatter, path) if frontmatter is not None else None
    successor = _scalar(frontmatter, "superseded-by") if frontmatter else ""
    review_by = _scalar(frontmatter, "review-by") if frontmatter else ""
    date = _scalar(frontmatter, "date") if frontmatter else ""

    return AdrRecord(
        number=number,
        adr_id=f"ADR-{number:03d}",
        filename=path.name,
        title=_extract_title(body, path),
        status=status,
        date=date,
        summary=_decision_summary(body),
        successor=successor or None,
        blocker=_blocking_condition(body),
        review_by=review_by,
    )


def is_adr_filename(name: str) -> bool:
    """True for a canonical ``ADR-NNN-slug.md`` filename.

    Public so ``build/scripts/build_all.py`` counts inputs by the same rule,
    rather than a glob that would count ``ADR-TEMPLATE.md`` as a record.
    """
    return _ADR_FILENAME_RE.match(name) is not None


def collect_records(adr_dir: Path) -> list[AdrRecord]:
    """Every canonical ADR under ``adr_dir``, sorted by the parsed integer, not
    by filename and not by iteration order, so output is filesystem-independent."""
    records = [
        build_record(path) for path in sorted(adr_dir.glob(_ADR_GLOB)) if is_adr_filename(path.name)
    ]
    records.sort(key=lambda r: r.number)
    return records


# --- Rendering ------------------------------------------------------------


def _cell(text: str) -> str:
    """Make ``text`` safe and short enough for one markdown table cell."""
    collapsed = " ".join(text.split()).replace("|", "\\|")
    if len(collapsed) > _CELL_MAX_CHARS:
        cut = collapsed[:_CELL_MAX_CHARS]
        space = cut.rfind(" ")
        if space > _CELL_MAX_CHARS // 2:
            cut = cut[:space]
        collapsed = cut.rstrip(" ,;:") + "..."
    # Unbalanced emphasis left by the cut renders as literal asterisks and can
    # swallow the rest of the row, so drop bold/italic runs and, when the cut
    # landed inside inline code, the stray backticks too.
    collapsed = collapsed.replace("**", "").replace("__", "")
    if collapsed.count("`") % 2:
        collapsed = collapsed.replace("`", "")
    return collapsed or "-"


def _link(record: AdrRecord) -> str:
    """Relative link to the record. README.md sits beside the ADRs."""
    return f"[{record.adr_id}]({record.filename})"


def _normalize_adr_id(reference: str) -> str | None:
    """Canonical ``ADR-NNN`` key for a frontmatter reference, or None.

    Accepts exactly what ``check_adr_lifecycle.py``'s ``_normalize_reference``
    accepts: ``ADR-091``, ``adr-91``, ``ADR 91``, ``ADR_91``, or a bare digit
    string. ``by_id`` keys are always the zero-padded ``ADR-{n:03d}`` form
    ``build_record`` assigns, so a non-padded or ADR-prefix-free reference such
    as ``ADR-91`` or ``91`` must be normalized to ``ADR-091`` before lookup, or
    a record that names a real, lifecycle-valid successor renders as an
    unlinked plain-text reference instead (Copilot, PR #5209, discussion
    flagging ``build/scripts/generate_adr_index.py:504``).
    """
    stripped = reference.strip()
    match = _ADR_REFERENCE_RE.match(stripped)
    if match is not None:
        return f"ADR-{int(match.group(1)):03d}"
    if stripped.isdigit():
        return f"ADR-{int(stripped):03d}"
    return None


def _successor_cell(record: AdrRecord, by_id: dict[str, AdrRecord]) -> str:
    """Where a reader who followed a stale citation should go instead.

    Walks ``superseded-by`` to the terminal record rather than printing the
    immediate successor. The two differ whenever a record was superseded twice:
    ADR-079 names ADR-091, which is itself retired in favour of ADR-092, so the
    immediate successor is a second dead end at the corpus front door. The
    frontmatter is right to name the immediate successor (ADR-073 supersession
    is an edge, and the chain is the history); the index is a redirect, and a
    redirect that lands on another redirect has not redirected.

    When the walk passes through intermediates, they are named after the
    terminal record so the chain stays visible.

    A retired record with no ``superseded-by`` is a dangling supersession, and
    the reader has nowhere to go. Say so, rather than print an empty cell that
    reads as "nothing to see".

    A cycle terminates the walk at its entry point rather than hanging. The
    lifecycle gate (``scripts/validation/check_adr_lifecycle.py``) reports
    cycles as violations; this renderer must not be the thing that discovers
    one by looping forever.
    """
    if not record.successor:
        return "not recorded"
    successor_id = _normalize_adr_id(record.successor)
    successor = by_id.get(successor_id) if successor_id is not None else None
    if successor is None:
        return _cell(record.successor)

    chain: list[AdrRecord] = []
    seen = {record.adr_id}
    current = successor
    while current.adr_id not in seen:
        chain.append(current)
        seen.add(current.adr_id)
        if current.status not in _RETIRED_STATUSES or not current.successor:
            break
        nxt_id = _normalize_adr_id(current.successor)
        nxt = by_id.get(nxt_id) if nxt_id is not None else None
        if nxt is None:
            break
        current = nxt

    terminal = chain[-1] if chain else successor
    if len(chain) <= 1:
        return _link(terminal)
    through = ", ".join(r.adr_id for r in chain[:-1])
    return f"{_link(terminal)} (via {through})"


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """Render a markdown table, or ``""`` when there are no rows."""
    body = list(rows)
    if not body:
        return ""
    out = ["| " + " | ".join(header) + " |"]
    out.append("| " + " | ".join("---" for _ in header) + " |")
    out.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(out) + "\n"


def _status_section(
    records: Sequence[AdrRecord], status: str, *, with_blocker: bool = False
) -> str:
    """Table for one status. Accepted, proposed and rejected share this shape."""
    header = ["ADR", "Title", "Date", "Decision"]
    if with_blocker:
        header.append("Blocking acceptance")
    rows = []
    for record in records:
        if record.status != status:
            continue
        row = [_link(record), _cell(record.title), _cell(record.date), _cell(record.summary)]
        if with_blocker:
            row.append(_cell(_blocker_cell(record)))
        rows.append(row)
    return _table(header, rows)


def _retired_section(records: Sequence[AdrRecord], by_id: dict[str, AdrRecord]) -> str:
    """Superseded and deprecated share one table: both need the same redirect."""
    rows = [
        [_link(r), _cell(r.title), r.status or "", _successor_cell(r, by_id)]
        for r in records
        if r.status in _RETIRED_STATUSES
    ]
    return _table(("ADR", "Title", "Status", "Read instead"), rows)


def _backfill_section(records: Sequence[AdrRecord]) -> str:
    """No status column: there is no status to report, and none is inferred."""
    rows = [[_link(r), _cell(r.title)] for r in records if r.status is None]
    return _table(("ADR", "Title"), rows)


_INTRO = (
    "# Architecture Decision Records\n\n"
    "Current state of the decision corpus, grouped by lifecycle status. Start here\n"
    "rather than grepping `ADR-*.md`: a keyword match in a superseded record reads\n"
    "exactly like a keyword match in an accepted one.\n\n"
    "Status comes from each record's YAML frontmatter (ADR-073), never from its prose.\n"
    "Regenerate after any ADR change with `uv run python build/scripts/build_all.py`.\n\n"
    "## Querying the corpus directly\n\n"
    "This table is a convenience, not the source of truth. The frontmatter is, and\n"
    "Python reads it with no extra dependency:\n\n"
    "```python\n"
    "import pathlib, re, yaml\n"
    "\n"
    "_CLOSING_FENCE = re.compile(r'\\r?\\n---\\r?\\n')\n"
    "\n"
    "for path in sorted(pathlib.Path('.agents/architecture').glob('ADR-[0-9]*.md')):\n"
    "    text = path.read_text(encoding='utf-8')\n"
    "    if not text.startswith('---'):\n"
    "        continue  # no frontmatter: see Needs backfill below\n"
    "    closing = _CLOSING_FENCE.search(text, 3)\n"
    "    if closing is None:\n"
    "        raise ValueError(f'{path.name}: opens with --- but never closes it')\n"
    "    front = yaml.safe_load(text[3 : closing.start()]) or {}\n"
    "    if str(front.get('status', '')).strip().lower() == 'accepted':\n"
    "        print(front.get('id') or path.name)\n"
    "```\n\n"
    "**Normalise before comparing, as above.** Both gates that bucket a record by\n"
    "status lower and strip it first: `_status_of` in\n"
    "`scripts/validation/check_adr_lifecycle.py` returns\n"
    "`str(value).strip().lower()`, and this generator does the same. So\n"
    "`status: Accepted` passes the `status-enum` gate and lands under Accepted in\n"
    "the table below, while a bare `== 'accepted'` misses it. Every record carries\n"
    "a lowercase value today, which is exactly why the mismatch would not announce\n"
    "itself.\n\n"
    "**This snippet does not detect duplicate keys, and the gates do.**\n"
    "`yaml.safe_load` resolves a repeated `status:` last-wins and silently, so a\n"
    "record declaring `proposed` in the line a human reads and `accepted` lower in\n"
    "the same block would print as accepted here. `check_adr_lifecycle` and this\n"
    "generator both reject that at the parser, so a corpus passing the gates has\n"
    "none. Run the gate before trusting a query on a tree you have not validated;\n"
    "the snippet is a convenience for reading a known-good corpus, not an\n"
    "independent check.\n\n"
    "Python rather than `yq` deliberately. Python is the repo's native tooling\n"
    "(ADR-042) and `yaml` is already a dependency, so this adds nothing. The `yq` on\n"
    "PATH here is the jq wrapper, which has no front-matter mode and fails on a\n"
    "markdown file; it needs a `sed` pre-extract and a subprocess per record. One\n"
    "documented method, not two, because a second one is redundancy that drifts.\n\n"
    "**Read the `continue` above before trusting any query.** A record with no\n"
    "frontmatter is invisible to every frontmatter query, so a count answers for the\n"
    "records that have it while appearing to answer for all of them. The Needs\n"
    "backfill section below is the honest denominator, and issue #5190 closes it.\n\n"
    "**This snippet crashes on unterminated frontmatter; it does not silently\n"
    "drop it.** `text.startswith('---')` is false only for a record with no\n"
    "schema at all, which `continue`s past. A record whose opening `---` fence\n"
    "never closes still starts with `---`, so it skips that `continue`, finds\n"
    "no match for `_CLOSING_FENCE`, and raises `ValueError` (verified by\n"
    "running both cases; Copilot found the original claim backwards on PR\n"
    "#5209). The real generator's `parse_frontmatter` raises the same way, on\n"
    "purpose: a malformed schema is an author's defect to see, not a record to\n"
    "drop quietly into Needs backfill. Run the gate rather than this snippet\n"
    "when that distinction matters.\n\n"
    "**The closing fence must occupy its own line, not just start one.**\n"
    "`generate_adr_index.py`'s `_FRONTMATTER_RE` is\n"
    "``r\"^---\\r?\\n([\\s\\S]*?)\\r?\\n---\\r?\\n([\\s\\S]*)$\"``: the closing fence is\n"
    "three dashes immediately followed by `\\r?\\n`, nothing else. An earlier\n"
    "version of this snippet used `text.index('\\n---', 3)`, which finds any\n"
    "line merely starting with three dashes, trailing characters or not. A\n"
    "closing line padded with one trailing space (`\"--- \\n\"` instead of\n"
    "`\"---\\n\"`, a plausible editor artifact) does not match `_FRONTMATTER_RE`,\n"
    "so `parse_frontmatter` finds no valid closing fence and raises\n"
    "`AdrIndexError`, the same as a fence that never closes at all. The old\n"
    "`.index` call could not tell the difference: it matched the padded line\n"
    "anyway and printed an answer with no error, silently disagreeing with the\n"
    "generator's correctly-loud rejection of the same file (Copilot, PR #5209\n"
    "round-5 review). `_CLOSING_FENCE` above requires the same `\\r?\\n` on both\n"
    "sides of the dashes as `_FRONTMATTER_RE`, so a padded or otherwise\n"
    "malformed fence now raises here too.\n\n"
)

# Heading order and the one-line orientation under each. Every heading renders
# even when its table is empty, so a reader can tell "no rejected ADRs" from "the
# Rejected section was dropped".
_BLURBS: tuple[tuple[str, str], ...] = (
    ("Accepted", "These bind today."),
    (
        "Proposed",
        "Recorded, not yet binding. The last column is what each record says is "
        "holding it short of acceptance.",
    ),
    (
        "Retired",
        "Superseded or deprecated. Do not cite these. The last column is where the decision moved.",
    ),
    (
        "Rejected",
        "Considered and declined. Kept visible so the proposal is findable and does not return.",
    ),
    (
        "Needs backfill",
        "No lifecycle frontmatter, so this index has no status to report. Nothing is "
        "inferred for these: open the record and read its `## Status` section. "
        "ADR-073 Phase 2 closes this section.",
    ),
)


def render_index(records: Sequence[AdrRecord]) -> str:
    """Render the full README. Same records in, byte-identical text out."""
    by_id = {r.adr_id: r for r in records}
    tables = {
        "Accepted": _status_section(records, "accepted"),
        "Proposed": _status_section(records, "proposed", with_blocker=True),
        "Retired": _retired_section(records, by_id),
        "Rejected": _status_section(records, "rejected"),
        "Needs backfill": _backfill_section(records),
    }
    parts = [_INTRO]
    for heading, blurb in _BLURBS:
        # An escape inside an f-string expression is 3.12+; the syntax floor is
        # 3.10 (.claude/rules/python.md), so the fallback is bound out here.
        table = tables[heading] or "None.\n"
        parts.append(f"## {heading}\n\n{blurb}\n\n{table}\n")
    return "".join(parts).rstrip("\n") + "\n"


# --- CLI ------------------------------------------------------------------


def generate(adr_dir: Path, output_path: Path) -> None:
    """Write the index to ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_index(collect_records(adr_dir)), encoding="utf-8")


def _run_check(adr_dir: Path, output_path: Path) -> int:
    """Compare the committed index to freshly generated content.

    ``records`` is bound once, ahead of ``render_index()``, so the ``OK``
    success line below can report how many ADR records were actually
    examined: a byte-for-byte match against an emptied or narrowed corpus
    would otherwise print the same unqualified ``OK`` as a match against
    the full one (Copilot, PR #5209 round-8 review). Unlike the equivalent
    fix in ``scripts/validation/check_adr_lifecycle.py`` and
    ``scripts/validation/check_adr_links.py``, no second, duplicate-cost
    read is needed here: ``render_index()`` already takes the record list
    as its argument rather than recomputing it internally, so splitting the
    one existing call is free.
    """
    records = collect_records(adr_dir)
    generated = render_index(records).replace("\r\n", "\n")
    fix = "To fix: uv run python build/scripts/generate_adr_index.py"
    if not output_path.exists():
        print(f"MISSING: {output_path} does not exist", file=sys.stderr)
        print(fix, file=sys.stderr)
        return 1
    committed = output_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if committed != generated:
        print(f"DRIFT: {output_path} differs from generated output", file=sys.stderr)
        print(fix, file=sys.stderr)
        return 1
    print(f"OK: {output_path} matches {adr_dir} ({len(records)} ADR record(s))")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate the ADR current-state index.")
    p.add_argument(
        "--adr-dir",
        type=Path,
        default=_ADR_DIR_RELATIVE,
        help="Directory holding ADR-NNN-slug.md records.",
    )
    p.add_argument(
        "--output", type=Path, default=_OUTPUT_RELATIVE, help="Path of the generated index."
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the committed index differs from the generated one.",
    )
    return p


def _resolve(path: Path) -> Path:
    """Resolve CLI paths against the repository root, not the caller CWD."""
    return path.resolve() if path.is_absolute() else (_REPO_ROOT / path).resolve()


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = build_parser().parse_args(argv)
    adr_dir = _resolve(args.adr_dir)
    output_path = _resolve(args.output)

    if not adr_dir.is_dir():
        print(f"Error: ADR directory not found: {adr_dir}", file=sys.stderr)
        return 2

    # An emptied or misrouted corpus (a wrong --adr-dir, or every record moved
    # out) still passes `adr_dir.is_dir()`, and `collect_records()` on zero
    # matches renders every index section as `None` and exits 0: a missing
    # corpus reads as valid generated output instead of failing loudly. Glob
    # via `is_adr_filename()`, not a bare `_ADR_GLOB` count, so `ADR-TEMPLATE.md`
    # sitting alone in the directory does not count as evidence records were
    # examined (Copilot, PR #5209 round-7 review).
    if not any(is_adr_filename(path.name) for path in adr_dir.glob(_ADR_GLOB)):
        print(f"Error: no ADR records found in {adr_dir}", file=sys.stderr)
        return 2

    try:
        if args.check:
            return _run_check(adr_dir, output_path)

        # .claude/rules/ci-scripts.md MUST 7: a script that resolves the
        # repository root and then writes to it must confirm the caller's cwd
        # sits inside that root before the first write. Relative
        # --adr-dir/--output args are already anchored to _REPO_ROOT by
        # _resolve() above, not to Path.cwd(); without this check, running the
        # script from a different worktree (or via a symlink into this one)
        # writes into _REPO_ROOT silently, with no signal that the write
        # landed outside the caller's own checkout. Mirrors
        # scripts/generate_third_party_notices.py:446-452 verbatim:
        #   project_root = PROJECT_ROOT
        #   if not Path.cwd().resolve().is_relative_to(project_root.resolve()):
        #       print(f"ERROR: current directory is outside project root: {Path.cwd()}", ...)
        #       return 2
        #
        # Scoped to this branch, not to every invocation: `_run_check()` above
        # is read-only, so a caller passing absolute --adr-dir/--output paths
        # from outside the repository has nothing to protect against there
        # (Copilot, PR #5209 round-7 review).
        if not Path.cwd().resolve().is_relative_to(_REPO_ROOT):
            print(
                f"Error: current directory is outside the repository root: {Path.cwd()}",
                file=sys.stderr,
            )
            return 2

        generate(adr_dir, output_path)
    except AdrIndexError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    print(f"Generated: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
