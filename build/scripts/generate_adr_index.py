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

`AGENTS.md` points every agent at `.agents/architecture/ADR-*.md`. That is
dozens of records and grows with every accepted decision, so "which decisions
bind me right now" gets answered by grepping a keyword and trusting the first
hit. A superseded PowerShell mandate and an accepted Python mandate look
identical to that reader. (Deliberately no exact count here: an earlier
version cited "98" and it went stale the moment the generated index below
examined a different number, Copilot, PR #5285 review.)

This is the consumer ADR-073 gated its deferred phases on. Its "Consumer trigger
and success metric" paragraph reads verbatim:

    **Consumer trigger and success metric.** Phases 2 to 4 proceed only when at
    least one concrete consumer is built: a stale-ADR detector, a generated
    current-state index, or a dependency viewer. Success is measured by that
    consumer reading frontmatter instead of scraping prose, and by zero
    prose-vs-frontmatter drifts surviving a gate run.

So `status`, `date` and `superseded-by` are read from frontmatter and never from
the body, running for every enum value the `status` query ADR-073 gives under
"Positive Consequences". The id comes from the filename, not from frontmatter:
some backfilled records carry no `id` key at all, while the filename is always
present and is the link a reader clicks. (Deliberately no fraction here: an
earlier version cited "10 of the 40" and it went stale the moment the bulk
frontmatter backfill dropped that count to near zero, Copilot, PR #5285
review.) Title, decision summary and blocking condition are quoted from the
body; the helpers below name where each comes from.

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
from urllib.parse import quote

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
# rendered as a string by _scalar() below.
#
# This is this module's own local contract, not a mirror of another script.
# A separate, unmerged branch (PR #5209) carries a lifecycle validation gate,
# check_adr_lifecycle.py, that accepts the same three reference shapes; that
# file is not part of this extraction (see the module docstring's "Why this
# is a small extraction" framing) and does not exist in this repository
# state, so it cannot be cited as a canonical source per
# .claude/rules/canonical-source-mirror.md (Copilot, PR #5285 review). If
# that gate lands later and its acceptance set diverges from this one, a
# record could pass lifecycle validation while the index fails to find its
# successor and prints the raw, unlinked reference instead; whoever lands it
# should reconcile the two patterns explicitly rather than assume parity.
_ADR_REFERENCE_RE = re.compile(r"^ADR[-_ ]?(\d+)$", re.IGNORECASE)

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
    carries `_has_duplicate_keys` with the docstring "Duplicate keys
    are malformed YAML and can hide a governance change (a second ``status:``
    line masking the first)", and fails its frontmatter-only exemption closed on
    them. That helper scans top-level lines with a regex; this loader hooks the
    parser instead, so it also catches duplicates nested inside a mapping value
    and is not fooled by quoting or comments.
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
    identically either way: there is no "(overdue)" suffix or other flag here.
    Detecting that a date has passed requires reading the wall clock, which
    this renderer must not do (it is required to be deterministic: same
    input, byte-identical output, and a clock read would make output depend
    on run date). Whether anything else in this repository flags an overdue
    ``review-by`` date is out of this module's scope to claim; nothing in
    this file does. The whole reason the field exists (issue #5193) is that
    ADR-002 and ADR-039 sat seven months past a provisional window nobody
    could see, and this cell's plain rendering has the same blind spot, one
    layer less deep: at least the date is visible here, where it was not
    visible at all before this field existed.
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
    adr_id = f"ADR-{number:03d}"
    # CRLF normalised once so every regex below sees a bare newline.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    frontmatter, body = parse_frontmatter(text, path)

    # The id is authoritatively the filename (module docstring: some
    # backfilled records carry no `id` key at all, while the filename is
    # always present and is the link a reader clicks), so a present-but-absent
    # `id` is not an error. A present `id` that disagrees with the filename is a
    # different defect: it means two different identities are on record for
    # one file, and a `superseded-by` elsewhere naming the frontmatter id
    # would resolve to the wrong record or appear dangling. Fail loudly and
    # name both, the same policy this module applies to every other
    # frontmatter defect (Copilot, PR #5285 review).
    id_value = _scalar(frontmatter, "id") if frontmatter else ""
    if id_value:
        normalized_id = _normalize_adr_id(id_value)
        if normalized_id != adr_id:
            raise AdrIndexError(
                f"{path.name}: frontmatter id {id_value!r} does not match the "
                f"filename-derived id {adr_id}"
            )

    status = _status_of(frontmatter, path) if frontmatter is not None else None
    successor = _scalar(frontmatter, "superseded-by") if frontmatter else ""
    review_by = _scalar(frontmatter, "review-by") if frontmatter else ""
    date = _scalar(frontmatter, "date") if frontmatter else ""

    return AdrRecord(
        number=number,
        adr_id=adr_id,
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
    """Relative link to the record. README.md sits beside the ADRs.

    ``_ADR_FILENAME_RE`` (``^ADR-(\\d{2,})-[^/]+\\.md$``) permits any
    non-slash character in the slug, including a space, ``#``, or an
    unmatched ``)``: none of those break the filename match, but a bare
    ``)`` inserted into a Markdown link destination closes the link early,
    and a ``#`` starts a fragment instead of naming a literal character.
    Percent-encode the path segment so the destination is well-formed
    regardless of what the slug contains (Copilot, PR #5285 review).
    """
    return f"[{record.adr_id}]({quote(record.filename)})"


def _normalize_adr_id(reference: str) -> str | None:
    """Canonical ``ADR-NNN`` key for a frontmatter reference, or None.

    Accepts the same reference shapes ``_ADR_REFERENCE_RE`` matches:
    ``ADR-091``, ``adr-91``, ``ADR 91``, ``ADR_91``, or a bare digit string.
    ``by_id`` keys are always the zero-padded ``ADR-{n:03d}`` form
    ``build_record`` assigns, so a non-padded or ADR-prefix-free reference such
    as ``ADR-91`` or ``91`` must be normalized to ``ADR-091`` before lookup, or
    a record that names a real successor renders as an unlinked plain-text
    reference instead.
    """
    stripped = reference.strip()
    match = _ADR_REFERENCE_RE.match(stripped)
    if match is not None:
        return f"ADR-{int(match.group(1)):03d}"
    if stripped.isdigit():
        return f"ADR-{int(stripped):03d}"
    return None


@dataclass(frozen=True, slots=True)
class _ChainWalk:
    """Result of walking a ``superseded-by`` chain from one hop past ``record``.

    Exactly one of ``cycle``, ``dangling_ref``, or ``dangling_no_successor``
    is set on an unresolved walk; none are set when the walk reached a real,
    non-retired terminal. Split out of ``_successor_cell`` so the walk's own
    branching and the rendering dispatch each stay under the cyclomatic
    complexity ceiling in ``.claude/rules/code-quality.md`` (taste-lint,
    PR #5285 review).
    """

    chain: list[AdrRecord]
    cycle: bool = False
    repeat_id: str = ""
    dangling_ref: str | None = None
    dangling_no_successor: bool = False


def _walk_supersession_chain(
    record: AdrRecord, successor: AdrRecord, by_id: dict[str, AdrRecord]
) -> _ChainWalk:
    """Walk ``superseded-by`` from ``successor`` to a terminal, a cycle, or a dead end."""
    chain: list[AdrRecord] = []
    seen = {record.adr_id}
    current = successor
    while current.adr_id not in seen:
        chain.append(current)
        seen.add(current.adr_id)
        if current.status not in _RETIRED_STATUSES:
            return _ChainWalk(chain)
        if not current.successor:
            # `current` (already appended to chain above) is itself retired
            # with no `superseded-by` at all: the same "not recorded" dead
            # end the `not record.successor` check in _successor_cell reports
            # for record's own first hop, but here on an intermediate.
            # Falling through to a resolved terminal would link to `current`
            # as if it were resolved, when it is a dangling supersession with
            # nowhere to send the reader (Copilot, PR #5285 review).
            return _ChainWalk(chain, dangling_no_successor=True)
        nxt_id = _normalize_adr_id(current.successor)
        nxt = by_id.get(nxt_id) if nxt_id is not None else None
        if nxt is None:
            # `current` is retired and names a successor this corpus has no
            # record for: the same dangling-reference problem
            # `_successor_cell` handles for record's own first hop, but here
            # it is an intermediate, whose own citation is a dead end
            # (AI Spec Validator, PR #5285 review).
            return _ChainWalk(chain, dangling_ref=current.successor)
        current = nxt
    # The while condition went false: `current` revisited a node already in
    # `seen`, so every record walked is retired with nowhere to land.
    return _ChainWalk(chain, cycle=True, repeat_id=current.adr_id)


def _successor_cell(record: AdrRecord, by_id: dict[str, AdrRecord]) -> str:
    """Where a reader who followed a stale citation should go instead.

    Walks ``superseded-by`` to the terminal record rather than printing the
    immediate successor. The two differ whenever a record was superseded twice:
    if A names B, and B is itself retired in favour of C, then A's immediate
    successor is a second dead end at the corpus front door. The frontmatter is
    right to name the immediate successor (ADR-073 supersession is an edge, and
    the chain is the history); the index is a redirect, and a redirect that
    lands on another redirect has not redirected. (No two-hop chain exists in
    the current corpus to cite by real id without the example rotting the next
    time either record's frontmatter changes; see
    ``test_two_hop_supersession_redirects_to_the_terminal_record`` for the
    synthetic case this docstring describes.)

    When the walk passes through intermediates, they are named after the
    terminal record so the chain stays visible.

    A retired record with no ``superseded-by`` is a dangling supersession, and
    the reader has nowhere to go. Say so, rather than print an empty cell that
    reads as "nothing to see". Two variants of this reach the walk instead of
    ``record`` itself: A retired in favour of B, where B is retired in favour
    of a ``superseded-by`` value with no matching record (``dangling_ref``),
    and A retired in favour of B, where B is retired but names no successor
    at all (``dangling_no_successor``). Both link to B as though it were a
    resolved terminal if left unhandled, repeating the redirect-to-a-redirect
    problem, so both are reported as unresolved rather than silently treating
    the last reachable record as the destination.

    A cycle (A retired in favour of B, B retired in favour of A, however many
    hops apart) has no terminal to redirect to: every record on it is
    retired, and the walk would otherwise pick "whichever one it revisited
    first" and print that as if it were a resolved destination, which is
    wrong in the same way printing an unresolved reference as a live link
    would be. This module ships with no gate elsewhere in this branch that
    rejects such a cycle before it reaches the renderer (Copilot, PR #5285
    review), so the renderer detects it itself and says so explicitly rather
    than publishing one retired record as if it were the other's fix.
    """
    if not record.successor:
        return "not recorded"
    successor_id = _normalize_adr_id(record.successor)
    successor = by_id.get(successor_id) if successor_id is not None else None
    if successor is None:
        # The same dangling-reference shape _walk_supersession_chain reports
        # for an intermediate hop (walk.dangling_ref below), but here it is
        # record's own first hop: report it the same way instead of printing
        # the bare reference text as though it might be a live link (Copilot,
        # PR #5285 review).
        return f"unresolved ({record.adr_id} -> {_cell(record.successor)})"

    walk = _walk_supersession_chain(record, successor, by_id)
    chain = walk.chain

    if walk.cycle:
        # Close the loop at the node that was actually revisited
        # (walk.repeat_id), not unconditionally at record.adr_id: record may
        # only lead into a cycle among later records without being part of
        # it itself (A -> B -> C -> D -> C, where the cycle is C <-> D and A,
        # B are not on it), and closing on record.adr_id there invents an
        # edge back to A that never exists (Cursor Bugbot, PR #5285 review).
        # repeat_id equals record.adr_id whenever record itself sits on the
        # cycle, so a one-hop self-reference (A names itself) and a direct
        # mutual pair (A <-> B) still close on record.adr_id as before.
        loop = " -> ".join([record.adr_id, *(r.adr_id for r in chain), walk.repeat_id])
        return f"cycle, unresolved ({loop})"

    if walk.dangling_ref is not None:
        path = " -> ".join([record.adr_id, *(r.adr_id for r in chain)])
        return f"unresolved ({path} -> {_cell(walk.dangling_ref)})"

    if walk.dangling_no_successor:
        path = " -> ".join([record.adr_id, *(r.adr_id for r in chain)])
        return f"unresolved ({path}, no successor recorded)"

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
    "_ADR_FILENAME_RE = re.compile(r'^ADR-(\\d{2,})-[^/]+\\.md$')\n"
    "_FRONTMATTER_RE = re.compile(r'^---\\r?\\n([\\s\\S]*?)\\r?\\n---\\r?\\n([\\s\\S]*)$')\n"
    "\n"
    "for path in sorted(pathlib.Path('.agents/architecture').glob('ADR-*.md')):\n"
    "    if not _ADR_FILENAME_RE.match(path.name):\n"
    "        continue  # not a canonical ADR record filename\n"
    "    text = path.read_text(encoding='utf-8')\n"
    "    match = _FRONTMATTER_RE.match(text)\n"
    "    if match is None:\n"
    "        if text.startswith('---'):\n"
    "            raise ValueError(f'{path.name}: opens with --- but never closes it')\n"
    "        continue  # no frontmatter: see Needs backfill below\n"
    "    front = yaml.safe_load(match.group(1)) or {}\n"
    "    if str(front.get('status', '')).strip().lower() == 'accepted':\n"
    "        print(front.get('id') or path.name)\n"
    "```\n\n"
    "**Normalise before comparing, as above.** This generator's own `_status_of`\n"
    "strips and lower-cases a string value before bucketing a record\n"
    "(`raw.strip().lower()`, after confirming `raw` is a string; see the next\n"
    "paragraph), so `status: Accepted` lands under Accepted in the table below,\n"
    "while a bare `== 'accepted'` misses it. Every record carries a lowercase\n"
    "value today, which is exactly why the mismatch would not announce itself.\n\n"
    "**This snippet trusts the corpus; the generator does not.** `_status_of`\n"
    "raises when a `status` value is present but not a string, before it ever\n"
    "strips or lower-cases anything, so `status: true` or `status: 1` fails the\n"
    "committed index loudly. The bare `str(front.get('status', ''))` above has no\n"
    "such check: it silently stringifies whatever YAML parsed, so a non-string\n"
    "value it happens to compare unequal to `'accepted'` passes through unnoticed\n"
    "instead of raising. This snippet is a read of a corpus the generator has\n"
    "already validated, not a second validator; regenerate the index (which does\n"
    "raise) before trusting a bare frontmatter query on a tree you have not.\n\n"
    "**This snippet does not detect duplicate keys, and the generator does.**\n"
    "`yaml.safe_load` resolves a repeated `status:` last-wins and silently, so a\n"
    "record declaring `proposed` in the line a human reads and `accepted` lower in\n"
    "the same block would print as accepted here. This generator's own frontmatter\n"
    "parser rejects that at the parser (a strict YAML loader that raises on a\n"
    "duplicate mapping key), so the committed index has none. Regenerate before\n"
    "trusting a query on a tree you have not; the snippet is a convenience for\n"
    "reading a known-good corpus, not an independent check.\n\n"
    "Python rather than `yq` deliberately. Python is the repo's native tooling\n"
    "(ADR-042) and `yaml` is already a dependency, so this adds nothing. The `yq` on\n"
    "PATH here is the jq wrapper, which has no front-matter mode and fails on a\n"
    "markdown file; it needs a `sed` pre-extract and a subprocess per record. One\n"
    "documented method, not two, because a second one is redundancy that drifts.\n\n"
    "**Read the `continue` above before trusting any query.** A record with no\n"
    "frontmatter is invisible to every frontmatter query, so a count answers for the\n"
    "records that have it while appearing to answer for all of them. The Needs\n"
    "backfill section below is the honest denominator, and issue #5190 closes it.\n\n"
    "**This snippet crashes on unterminated or malformed frontmatter; it does\n"
    "not silently drop it.** `_FRONTMATTER_RE` above is the generator's own\n"
    "pattern, quoted verbatim, so `match = _FRONTMATTER_RE.match(text)` fails\n"
    "to match for two different reasons the snippet must not conflate: a\n"
    "record with no schema at all, and a record that opens with `---` but\n"
    "never reaches a valid, exact closing fence (an unterminated block, or a\n"
    "malformed opening line such as `\"--- \\n\"` with a trailing space before\n"
    "the newline, which fails the same `^---\\r?\\n` the generator requires).\n"
    "The snippet disambiguates them exactly as `parse_frontmatter` does: a\n"
    "literal `text.startswith('---')` check, not a regex, decides `raise` from\n"
    "`continue`. An earlier version of this snippet used its own\n"
    "`_OPENING_FENCE` regex for that decision instead of the literal prefix\n"
    "check, so a malformed opening line failed `_OPENING_FENCE` the same way it\n"
    "failed `_FRONTMATTER_RE` and the snippet `continue`d past it as though the\n"
    "record had no frontmatter, printing an incomplete accepted set for a\n"
    "corpus the generator would reject outright (Copilot, PR #5285 review).\n"
    "Reusing the exact `text.startswith('---')` predicate `parse_frontmatter`\n"
    "uses is what keeps the two in agreement. The real generator raises here on\n"
    "purpose: a malformed schema is an author's defect to see, not a record to\n"
    "drop quietly into Needs backfill.\n\n"
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
        "No machine-readable lifecycle status: either the record carries no "
        "frontmatter block at all, or its frontmatter is present but omits the "
        "`status` key. Either way this index has nothing to report. Nothing is "
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
    the full one. No second, duplicate-cost read is needed to get that
    count: ``render_index()`` already takes the record list as its argument
    rather than recomputing it internally, so splitting the one existing
    call is free.
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
        # sits inside that root before the first write. The risk this guards
        # against is *implicit* resolution: a relative --adr-dir/--output is
        # anchored to _REPO_ROOT by _resolve() above, not to Path.cwd(), so
        # running the script bare from a different worktree writes into
        # _REPO_ROOT silently, with no signal the write landed outside the
        # caller's own checkout. Mirrors scripts/generate_third_party_notices.py:446-452
        # verbatim:
        #   project_root = PROJECT_ROOT
        #   if not Path.cwd().resolve().is_relative_to(project_root.resolve()):
        #       print(f"ERROR: current directory is outside project root: {Path.cwd()}", ...)
        #       return 2
        #
        # Stricter/looser/different than canonical: that script has no
        # CLI override, so PROJECT_ROOT is always both the resolution anchor
        # and the write target, and cwd-vs-PROJECT_ROOT is the only check
        # possible. This script's --adr-dir/--output CAN be absolute, and
        # build_all._build_adr_index always passes them that way, resolved
        # from its own caller-supplied repo_root (itself build_all.py's own
        # --repo-root CLI flag, a real, exposed override, not test-only).
        # Checking cwd against _REPO_ROOT unconditionally, including for an
        # absolute, caller-typed target elsewhere, verifies nothing about
        # that target: it neither catches a real mismatch (cwd can equal
        # _REPO_ROOT while --adr-dir points at an unrelated tree) nor avoids
        # a false rejection (a legitimate --repo-root invocation of
        # build_all.py whose cwd sits outside this script's own checkout)
        # (Copilot, PR #5285 review). An absolute path is a stated write
        # target the caller supplied explicitly; cwd cannot silently redirect
        # it the way it can a relative one, so the guard is scoped to the
        # case it actually protects: implicit resolution against _REPO_ROOT
        # for a relative --adr-dir or --output.
        if not args.adr_dir.is_absolute() or not args.output.is_absolute():
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
