#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: the rule's own remediation is to split into
# `_helpers.py`, `_types.py`, and `_constants.py`. That is the wrong shape here.
# This is one CLI that owns three coupled invariants (scan the corpus, compare
# per-check counts against a frozen baseline, rewrite that baseline atomically),
# and `.claude/rules/unified-software-engineering.md` rejects "shallow
# pass-through layers" and "wrappers that add names but no simplification".
# Splitting an eight-check gate across four modules would put the check list, the
# violation type, and the ratchet arithmetic in different files that must be
# read together to answer any question about the gate. The executable code
# alone, with every docstring stripped, is still well over the 500-line
# ceiling (a volatile exact count is deliberately not repeated here: an
# earlier version pinned this suppression's evidence to a specific line
# count and a specific "eight-check" claim, and both drifted stale on the
# very next edit, Copilot, PR #5209 round-10 review), and those docstrings
# carry the verbatim ADR-073 schema quote and the `_split_frontmatter`
# divergence section that `.claude/rules/canonical-source-mirror.md`
# requires. Precedent in this directory: `check_doc_interpreter_portability.py`
# carries the same suppression for the same reason, "one CLI owns scan,
# ratchet, and atomic update invariants". Issue #3779 documents this escape;
# issue #5191 is the work.
"""Ratcheted lifecycle gate over `.agents/architecture/ADR-NNN-*.md` (issue #5191).

`check_adr_uniqueness.py` is the only other deterministic ADR gate and it reads
filenames alone, so nothing reads what an ADR says about its own lifecycle state.
Every defect in the issue #5191 audit reached `main` unopposed: 59 of 98 records
carry no frontmatter, 6 are `proposed` while `implemented: true`, ADR-091 claims
to supersede ADR-079 while ADR-079 names ADR-092 as its successor, and 7 records
carry frontmatter with no `## Status` section. This gate closes the first and
third of those (`frontmatter-parses`, `supersession-target-exists`); the other
two are intentionally not violations here, not gaps this gate missed:
`implemented: true` with `proposed` is deliberate per ADR-098 (the removed
eighth check below), and `prose-frontmatter-agree` skips a record with no
`## Status` section instead of flagging it, since ADR-073 makes the frontmatter
enum authoritative (Copilot, PR #5209 round-7 review).

The schema enforced here is ADR-073 (`ADR-073-adr-lifecycle-frontmatter.md`),
whose Decision section defines the block verbatim as::

    id: ADR-NNN
    status: proposed | accepted | rejected | deprecated | superseded   # enum, no prose
    date: YYYY-MM-DD          # last updated
    decision-makers: []
    supersedes: []            # ADR ids this record supersedes
    superseded-by: null       # ADR id that supersedes this record, or null
    explainer: null           # link to a living design doc, if paired
    implemented: false        # flips true at first merged change; gates amend-vs-supersede

That ADR binds one behavior, quoted verbatim: "When the two disagree, the
frontmatter wins, the gate flags the drift, and the author reconciles by editing
the prose to match; the gate never silently rewrites prose." This gate is
read-only. It opens ADR files and never writes one.

Stricter/looser/different than canonical: ADR-073 defers enforcement to
"Phases 3 to 4 (enforce; deferred, consumer-gated)" and warns that a gate
"becomes a tripwire on any un-migrated record". This gate is looser than that
enforcement in the way the ADR's own Phase-2 concern demands: it is a per-check
RATCHET, not a cliff. Every current violation is recorded in
`adr_lifecycle_baseline.json` and passes; only a RISE in a check's count fails.
Each run prints which checks sit at zero and could be flipped to zero-tolerance.

Checks, each named so the baseline tracks them separately:

    frontmatter-parses           leading `---` block exists and safe_loads to a mapping
    id-matches-filename          frontmatter `id` equals the filename's ADR number
    status-enum                  status is one of the five lifecycle values
    supersession-reciprocal      X.superseded-by: Y implies Y.supersedes contains X
    supersession-target-exists   every named id resolves to a file; no self-supersession
    proposed-cannot-supersede    a `proposed` record may not declare `supersedes`
    prose-frontmatter-agree      the first `## Status` line matches the frontmatter enum
    status-edge-consistency      status: superseded iff a superseded-by edge resolves

`status-edge-consistency` closes a gap `supersession-reciprocal` leaves open
(Copilot, PR #5209): reciprocity validates edges against each other, never
against the status enum, so a record can read `status: accepted` while its
own `superseded-by` names a live successor, or read `status: superseded`
with no successor at all. `deprecated` is deliberately exempt from the
"superseded needs an edge" direction: ADR-098 documents that status for a
record that shipped and was later abandoned with no specific named
successor, not a supersession.

An eighth check, `implemented-implies-decided` (`implemented: true` with
`status: proposed`), was removed: ADR-073's own schema defines `implemented`
as flipping at first merged change independent of decision state, and
ADR-098 documents that exact pairing as deliberate. See `_check_lifecycle_rules`
for the full removal rationale.

Checks 2 to 7 need parseable frontmatter, so a record failing `frontmatter-parses`
contributes one violation, not seven. The same containment runs downstream:
`prose-frontmatter-agree` is skipped when the status section is absent
(the record simply has no prose status) or the enum value is invalid (`status-enum`
owns that), and `supersession-reciprocal` ignores an edge that
`supersession-target-exists` already rejected. Without it one defect would
inflate several counts and the baseline would move for reasons the author did
not cause.

Exit codes (per ADR-035):
    0 - no check exceeds its baseline (improvements pass and are reported)
    1 - at least one check rose above its baseline
    2 - config error (ADR directory missing, baseline missing/malformed/stale)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils.markdown_parser import blank_non_prose_block_lines

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from yaml_utils import _parse_yaml_frontmatter  # noqa: E402

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2

CHECKS: tuple[str, ...] = (
    "frontmatter-parses",
    "id-matches-filename",
    "status-enum",
    "supersession-reciprocal",
    "supersession-target-exists",
    "proposed-cannot-supersede",
    "prose-frontmatter-agree",
    "status-edge-consistency",
)

# ADR-073 Decision section, verbatim: "status: proposed | accepted | rejected |
# deprecated | superseded   # enum, no prose".
LIFECYCLE_STATUSES: frozenset[str] = frozenset(
    {"proposed", "accepted", "rejected", "deprecated", "superseded"}
)

# Mirrors ADR_FILENAME_RE in scripts/validation/check_adr_uniqueness.py, quoted
# verbatim: r"^ADR-(\d{2,})-[^/]+\.md$". Identical so the two ADR gates never
# disagree about which files are ADRs.
ADR_FILENAME_RE = re.compile(r"^ADR-(\d{2,})-[^/]+\.md$")

# An id reference inside frontmatter: "ADR-091", "adr-91", or a bare integer.
_ADR_REFERENCE_RE = re.compile(r"^ADR[-_ ]?(\d{1,4})$", re.IGNORECASE)

# `## Status`, optionally indented, on its own line. Level two only: a
# `### Status` is a subsection of whatever contains it, never the record's own.
# See `_status_prose` for why this one is searched across the whole body while
# the inline form below stays bounded to the record header.
_STATUS_HEADING_RE = re.compile(r"(?m)^[ \t]{0,3}##[ \t]+Status[ \t]*$", re.IGNORECASE)

# The inline form ADR-055 uses: `**Status**: Accepted (supersedes ADR-024, ...)`.
# The bold marker is required. A bare body line reading `status: x` is prose or a
# code sample, not a status declaration, and must not be read as one.
_INLINE_STATUS_RE = re.compile(r"(?m)^[ \t]{0,3}\*\*Status\*\*[ \t]*:[ \t]*(.+)$")

# Level-2 headings only. `_record_header` uses these to bound the *inline*
# status search; the `## Status` section search is not bounded this way.
_LEVEL_TWO_HEADING_RE = re.compile(r"(?m)^[ \t]{0,3}##[ \t]+(.+?)[ \t]*$")

# Leading lifecycle word through any decoration: "**Accepted**", "> Superseded
# by ADR-094 (2026-08-15)", "`Proposed`. Supersedes ADR-036."
_LEAD_WORD_RE = re.compile(r"^[*_`~>\[\s]*([A-Za-z]+)")

_BASELINE_PATH = Path(__file__).with_name("adr_lifecycle_baseline.json")

_BASELINE_DESCRIPTION = (
    "Per-check ADR lifecycle violation ceiling (issue #5191). A count may fall "
    "but never rise. Regenerate with: uv run python "
    "scripts/validation/check_adr_lifecycle.py --write-baseline"
)


@dataclass(frozen=True, slots=True)
class Violation:
    """One finding, attributed to exactly one check name."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        return f"{self.path}: [{self.check}] {self.detail}"


@dataclass(frozen=True, slots=True)
class Record:
    """One ADR file, parsed as far as it could be."""

    number: int
    path: str
    frontmatter: dict[str, Any] | None
    body: str


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    r"""Return ``(raw frontmatter block, body)``; the block is None when absent.

    The boundary arithmetic mirrors ``_parse_yaml_frontmatter`` in
    ``scripts/validation/yaml_utils.py``, quoted verbatim::

        if not text.startswith("---"):
            return None
        end_index = text.find("\n---", 3)
        if end_index == -1:
            return None
        frontmatter_text = text[4:end_index].strip()

    Stricter/looser/different than canonical: identical boundaries, but this also
    returns the body, which that helper discards. The body is what
    ``prose-frontmatter-agree`` reads, so the split
    cannot be delegated. The parsed mapping still comes from the canonical helper
    (see :func:`_read_record`), so one parser decides what a valid mapping is.
    """
    if not text.startswith("---"):
        return None, text
    end_index = text.find("\n---", 3)
    if end_index == -1:
        return None, text
    return text[4:end_index].strip(), text[end_index + len("\n---") :]


def _frontmatter_reason(raw: str | None, text: str) -> str:
    """Human-readable reason a frontmatter block is unusable.

    ``_parse_yaml_frontmatter`` collapses "absent", "malformed", and "not a
    mapping" into one None and discards the YAML parser error. Re-deriving the
    reason follows the precedent of ``_frontmatter_error`` in
    ``scripts/validation/validate_copilot_agent_frontmatter.py``, whose comment
    states the same rationale: "that helper swallows the error to None, but
    issue #2500 requires the YAML parser error in the message".

    ``raw`` is None for two different defects, and ``text`` is what separates
    them. ``_split_frontmatter`` returns None when the file does not start with
    ``---`` (the block is absent) and also when it starts with ``---`` but no
    closing fence follows (the block is unterminated). Reporting both as
    "no leading `---` frontmatter block" sends an author to add frontmatter that
    is already there: a record can open with ``---`` and carry ``id``,
    ``status`` and ``date``, and still be told its schema is absent. The record
    was always reported, so this is a wrong diagnosis rather than a silent drop,
    and no count moves.

    The two branches test exactly what ``_split_frontmatter`` tested, so the
    message always describes why the split returned None. It deliberately does
    not re-derive markdown semantics: a leading ``----`` horizontal rule is
    reported as an unterminated block because that is how the splitter, and the
    canonical helper it mirrors, classify it.
    """
    if raw is None:
        if text.startswith("---"):
            return (
                "frontmatter block opens with `---` but no closing `---` fence "
                "follows, so the whole block is unreadable (ADR-073 schema unparsed)"
            )
        return "no leading `---` frontmatter block (ADR-073 schema absent)"
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return f"frontmatter YAML did not parse: {' '.join(str(exc).split())}"
    if parsed is None:
        return "frontmatter block is empty"
    return f"frontmatter is a {type(parsed).__name__}, not a YAML mapping"


class _DuplicateKey(yaml.YAMLError):
    """A frontmatter mapping declared the same key twice. Carries the key."""

    def __init__(self, key: object) -> None:
        super().__init__(f"duplicate key {key!r}")
        self.key = key


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of taking the last."""


def _reject_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    """Mirror of `_no_duplicate_keys` in build/scripts/generate_adr_index.py.

    Quoted verbatim from that file, which is the canonical implementation:

        seen: list[Any] = []
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            if any(key == earlier for earlier in seen):
                raise _DuplicateKeyError(...)
            seen.append(key)

    Stricter/looser/different than canonical: identical detection, but this
    raises an error carrying the key object so `_read_record` can name it in the
    violation. The index generator only needs to fail the build.

    A list compared with `==`, not a set: a YAML key need not be hashable
    (`? [a, b]` builds a list key), and a set raises `TypeError` on it. See the
    canonical docstring for the escape that shape produced.
    """
    seen: list[Any] = []
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if any(key == earlier for earlier in seen):
            raise _DuplicateKey(key)
        seen.append(key)
    mapping: dict[Any, Any] = loader.construct_mapping(node, deep=True)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _reject_duplicate_keys
)


def _duplicate_key(raw: str | None) -> str | None:
    """Return the first key declared twice, rendered for the message, or None.

    PyYAML resolves duplicates last-wins and reports nothing, so a record
    carrying `status: proposed` near the top and `status: accepted` lower in the
    same block parses as accepted while reading as proposed to anyone scanning
    the first lines. For a lifecycle gate that is a forgery vector, not a
    formatting nit: the declaration a human sees and the one tooling enforces
    are different values.

    Detected at the parser, not by scanning lines. An earlier revision compared
    raw line prefixes, which asks a different question than YAML does: `status`
    and `"status"` are one key to the parser and two distinct strings to a line
    scan. Measured on that revision, two of four spellings walked straight
    through the guard while `yaml.safe_load` enforced `accepted` for all four:

        status: proposed  / status: accepted      caught
        "status": proposed / status: accepted     MISSED
        status : proposed / status: accepted      caught
        'status': proposed / status: accepted     MISSED

    A guard against forgery that the forger can evade by adding quotation marks
    is worse than none, because it reports clean. Copilot found it on PR #5230.

    Widened by the same change: the parser sees nested mappings too, so a
    duplicate inside a mapping value is now caught. A line scan structurally
    cannot do that, which is why the three ADR readers no longer each use a
    different mechanism.

    Malformed YAML returns None rather than raising. This runs before
    `_parse_yaml_frontmatter`, and `_frontmatter_reason` owns the parse-failure
    message; reporting it here too would count one defect twice.
    """
    if raw is None:
        return None
    try:
        yaml.load(raw, Loader=_StrictLoader)
    except _DuplicateKey as exc:
        return exc.key if isinstance(exc.key, str) else repr(exc.key)
    except yaml.YAMLError:
        return None
    return None


def _read_record(path: Path, number: int, rel: str) -> tuple[Record, Violation | None]:
    """Parse one ADR. The violation is non-None when the frontmatter is unusable."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        empty = Record(number, rel, None, "")
        return empty, Violation("frontmatter-parses", rel, f"could not be read: {exc}")
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError subclasses ValueError, not OSError, so the handler
        # above never sees it. Without this arm one record with a stray byte
        # aborts the whole gate with a traceback, which reports nothing about
        # the other 97 records and reads as tooling breakage rather than as a
        # finding about the corpus. Reported as its own violation with a
        # distinct message, because "not valid UTF-8" and "could not be read"
        # call for different fixes.
        empty = Record(number, rel, None, "")
        return empty, Violation("frontmatter-parses", rel, f"is not valid UTF-8: {exc}")
    raw, body = _split_frontmatter(text)
    duplicate = _duplicate_key(raw)
    if duplicate is not None:
        return (
            Record(number, rel, None, body),
            Violation(
                "frontmatter-parses",
                rel,
                f"declares `{duplicate}` twice; PyYAML keeps the last value "
                f"silently, so the visible declaration and the enforced one differ",
            ),
        )
    frontmatter = _parse_yaml_frontmatter(text)
    if frontmatter is None:
        return (
            Record(number, rel, None, body),
            Violation("frontmatter-parses", rel, _frontmatter_reason(raw, text)),
        )
    return Record(number, rel, frontmatter, body), None


def collect_records(adr_dir: Path, repo_root: Path) -> tuple[list[Record], list[Violation]]:
    """Read every `ADR-NNN-*.md` under ``adr_dir``, in filename order."""
    records: list[Record] = []
    violations: list[Violation] = []
    for md in sorted(adr_dir.glob("ADR-*.md")):
        match = ADR_FILENAME_RE.match(md.name)
        if not match:
            continue
        try:
            rel = md.relative_to(repo_root).as_posix()
        except ValueError:
            rel = md.name
        record, violation = _read_record(md, int(match.group(1)), rel)
        records.append(record)
        if violation is not None:
            violations.append(violation)
    return records, violations


def _frontmatter_of(record: Record) -> dict[str, Any]:
    """The parsed mapping. Callers must have filtered unparseable records."""
    if record.frontmatter is None:
        raise ValueError(f"{record.path} has no parsed frontmatter")
    return record.frontmatter


def _status_of(record: Record) -> str:
    """Lowercased frontmatter status, or "" when absent or non-scalar."""
    value = _frontmatter_of(record).get("status")
    if value is None or isinstance(value, (list, dict)):
        return ""
    return str(value).strip().lower()


def _normalize_reference(value: object) -> int | None:
    """ADR number named by a frontmatter reference, or None when unparseable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    match = _ADR_REFERENCE_RE.match(value.strip())
    return int(match.group(1)) if match else None


def _supersedes_entries(record: Record) -> list[Any] | None:
    """Raw ``supersedes`` entries, or None when the field is not list-shaped.

    A bare scalar is accepted as a one-element list. Authors write
    ``supersedes: ADR-004`` often enough that rejecting it would report a schema
    complaint where the intent is unambiguous.
    """
    value = _frontmatter_of(record).get("supersedes")
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return [value]
    return None


def _check_identity(record: Record) -> list[Violation]:
    """`id-matches-filename` and `status-enum` for one parsed record."""
    found: list[Violation] = []
    raw_id = _frontmatter_of(record).get("id")
    number = _normalize_reference(raw_id)
    if number is None:
        detail = f"frontmatter `id` is {raw_id!r}; expected ADR-{record.number:03d}"
        found.append(Violation("id-matches-filename", record.path, detail))
    elif number != record.number:
        detail = (
            f"frontmatter `id` names ADR-{number:03d} but the filename says ADR-{record.number:03d}"
        )
        found.append(Violation("id-matches-filename", record.path, detail))
    if _status_of(record) not in LIFECYCLE_STATUSES:
        detail = (
            f"status is {_frontmatter_of(record).get('status')!r}; ADR-073 allows "
            + " | ".join(sorted(LIFECYCLE_STATUSES))
        )
        found.append(Violation("status-enum", record.path, detail))
    return found


def _record_header(body: str) -> str:
    """The region where a bold `**Status**:` label states the record's status.

    Everything from the top of the body up to the first level-2 heading that is
    not `## Status`. Used by `_status_prose` for the inline form only; the
    `## Status` section is an explicit declaration and is searched everywhere.

    This bound is not cosmetic for the inline form. Without it the search runs
    the whole document and takes the first match anywhere, which is how
    ADR-055's `**Status**: COMPLETE` at line 119 (a phase result) and
    `**Status**: APPROVED` at line 168 (an exception ruling) were read as that
    record's lifecycle status. Both were masked while a real `## Status` section
    sat higher in the file and surfaced the moment it was removed.

    That is the same defect this campaign filed as issue #5189 against
    `_get_adr_status`, which regexed `^status:` across an entire ADR instead of
    its frontmatter. Scoping the search to the region that can legitimately hold
    the answer is the fix in both cases.

    Bounding *every* form this way was an over-correction that opened a bypass;
    see `_status_prose`. ADR-042's `### Status` at line 171 is excluded by
    `_STATUS_HEADING_RE` matching level two only, not by this bound.
    """
    for match in _LEVEL_TWO_HEADING_RE.finditer(body):
        if match.group(1).strip().lower() != "status":
            return body[: match.start()]
    return body


def _status_prose(body: str) -> str | None:
    """First non-blank line of the record's status section, or None when absent.

    A `## Status` heading with nothing under it returns "", which keeps
    prose present while `prose-frontmatter-agree` reports
    the missing lifecycle word.

    Three forms, scoped by what each one *is* rather than by where it sits.
    An earlier revision bounded every form to the record header, which fixed
    one bug and opened another: a `## Status` section placed after `## Context`
    became invisible, so moving the section silently bypassed the drift check.
    Nothing in ADR-073 or issue #5191 constrains section order. Copilot found it.

    `## Status`, level two, is searched across the **whole body**. It is an
    explicit section heading declaring the record's lifecycle state, and it
    means that wherever an author puts it.

    `**Status**: X`, a bold inline label, is searched in the **header region
    only**. A bold label is not a section, and it reads as the record's status
    only at the top, which is how the older records state it (ADR-006 line 3,
    ADR-035 line 5, both predating `## Status` sections). Deeper occurrences are
    something else: ADR-055 carries `**Status**: COMPLETE` at line 119 as a
    phase result and `**Status**: APPROVED` at line 168 as an exception ruling,
    and both were read as that record's lifecycle status before this bound.

    Fenced and indented code blocks, and raw HTML blocks, are blanked before
    any of this runs, so a `## Status` inside a markdown sample or an HTML
    comment is not read as the record's own. ADR-022 carries exactly such a
    sample at line 521, inside an ADR template it documents. It is masked
    today only because ADR-022's real `## Status` sits at line 3 and the
    search takes the first match; removing that section, which is the
    direction this campaign is already moving in, would expose it. A
    whole-body search without this is the same whole-file-scan defect the
    search was widened to fix, one layer down. Copilot found it on PR #5230.
    HTML blocks specifically: `blank_code_block_lines` (used until this fix)
    deliberately leaves HTML content visible for a different caller
    (`check_skill_md_portability.py`), so an HTML comment documenting a former
    `## Status` section, as ADR-TEMPLATE.md carries, was not masked and could
    be read as a live status declaration one layer below where the fence check
    already protects. `blank_non_prose_block_lines` closes that gap without
    touching the other caller's contract (PR #5209 review).

    `### Status`, level three, is **never** matched. A level-three heading is a
    subsection of whatever contains it. ADR-042 carries one at line 171 reading
    "Proposed" inside a migration phase while its frontmatter says `accepted`;
    matching it manufactured a drift violation out of a correct record.

    Raises whatever `blank_non_prose_block_lines` raises on an unparseable
    body. That helper's own contract (`scripts/utils/markdown_parser.py`,
    `_blank_block_lines`) requires the exception to propagate rather than be
    treated as clean prose; catching it here and returning `None` would do
    exactly that, since `None` means "no status section" to every caller and
    silently exempts the record from `prose-frontmatter-agree`. Callers that
    need per-record diagnostics catch this at the call site (see
    `_check_prose`) and turn it into a violation, not into a skip. Copilot
    found this on PR #5209.
    """
    prose = blank_non_prose_block_lines(body)
    heading = _STATUS_HEADING_RE.search(prose)
    if heading is not None:
        for line in prose[heading.end() :].splitlines():
            stripped = line.strip()
            if _LEVEL_TWO_HEADING_RE.match(line):
                return ""
            if stripped:
                return stripped
        return ""
    inline = _INLINE_STATUS_RE.search(_record_header(prose))
    return inline.group(1).strip() if inline is not None else None


def _check_prose(record: Record) -> list[Violation]:
    """`prose-frontmatter-agree` for one record.

    A record with no prose status section is NOT a violation. An earlier revision
    of this gate required one (`status-section-present`) and the repo owner
    rejected it on review of ADR-005: with `status: superseded` and
    `superseded-by: ADR-042` in frontmatter, a prose line reading "Superseded by
    ADR-042" is duplication, and duplication is a drift surface rather than a
    service to the reader.

    ADR-073 does choose dual representation: the Decision retains the prose
    section as a secondary rendering, so it stays in the template and this gate
    reads it wherever it appears. What it never states is that every record must
    restate the enum in prose; line 57 says the section "remains for humans and
    **may** carry the nuance the enum cannot". Turning presence into a MUST is a
    stronger rule than the ADR writes, and the owner declined it on the record
    that first tripped it. Making it mandatory is an ADR-073 amendment, not a
    validator default (raised on PR #5209).

    What survives is the rule ADR-073 does state: when prose and frontmatter both
    speak and disagree, frontmatter wins and the author reconciles the prose.
    Records like ADR-042 and ADR-055, whose prose carries debate-log citations and
    supersession reasoning, keep their sections and are still checked here.

    A record whose markdown will not parse is reported as a violation of this
    same check, not silently skipped. `_status_prose` lets the parser's
    exception propagate rather than swallow it into "no status section";
    catching it here and returning a violation is the difference between a
    counted finding and a record that quietly bypasses drift detection because
    its markdown happens to be unparseable (Copilot, PR #5209).
    """
    try:
        prose = _status_prose(record.body)
    except Exception as exc:
        detail = f"status prose could not be parsed: {exc}"
        return [Violation("prose-frontmatter-agree", record.path, detail)]
    if prose is None:
        return []
    status = _status_of(record)
    if status not in LIFECYCLE_STATUSES:
        # `status-enum` owns this defect; comparing prose against an invalid enum
        # value would report the same problem a second time.
        return []
    lead = _LEAD_WORD_RE.match(prose)
    if (lead.group(1).lower() if lead is not None else "") == status:
        return []
    detail = (
        f"frontmatter says status: {status}, but the status section opens with "
        f"{prose[:70]!r}. Frontmatter wins; edit the prose to match (ADR-073: the "
        "gate never rewrites prose)."
    )
    return [Violation("prose-frontmatter-agree", record.path, detail)]


def _check_lifecycle_rules(record: Record) -> list[Violation]:
    """`proposed-cannot-supersede`.

    This function used to also own `implemented-implies-decided`, blocking
    `implemented: true` with `status: proposed`. Removed (Copilot, PR #5209):
    ADR-073's own schema comment defines `implemented` as flipping "at first
    merged change", independent of decision state, and ADR-098 documents
    `status: proposed` with `implemented: true` as a deliberate pairing for
    exactly this reason (a governance ADR's own acceptance is a maintainer
    act, not something its own debate log can self-assert). The corpus
    already carries six such records by design (ADR-075, ADR-077, ADR-078,
    ADR-089, ADR-093, ADR-098; see ADR-055's Provenance section), all
    baselined at the removed check's full count. A blocking gate against a
    pattern the canonical schema and a live record both call deliberate is a
    gate encoding an invariant the corpus rejects, not the corpus drifting.
    """
    if _status_of(record) != "proposed":
        return []
    entries = _supersedes_entries(record)
    if not entries:
        return []
    detail = (
        f"status is proposed but it declares supersedes: {entries}. A proposal "
        "cannot retire an accepted decision."
    )
    return [Violation("proposed-cannot-supersede", record.path, detail)]


def _edge_targets(
    record: Record, raw_entries: list[Any], field: str, known: set[int]
) -> tuple[list[int], list[Violation]]:
    """Resolve id references into usable targets plus target-exists findings."""
    targets: list[int] = []
    found: list[Violation] = []
    for entry in raw_entries:
        number = _normalize_reference(entry)
        if number is None:
            detail = f"`{field}` entry {entry!r} is not an ADR id"
        elif number == record.number:
            detail = f"`{field}` names itself (ADR-{number:03d}); a record cannot supersede itself"
        elif number not in known:
            detail = (
                f"`{field}` names ADR-{number:03d}, which has no file under .agents/architecture/"
            )
        else:
            targets.append(number)
            continue
        found.append(Violation("supersession-target-exists", record.path, detail))
    return targets, found


@dataclass(frozen=True, slots=True)
class _Graph:
    """Resolved supersession edges plus the findings that resolving them produced."""

    successor: dict[int, int]
    predecessors: dict[int, set[int]]
    findings: list[Violation]


def _build_graph(by_number: dict[int, Record], known: set[int]) -> _Graph:
    """Resolve every `supersedes` and `superseded-by` edge in the corpus."""
    successor: dict[int, int] = {}
    predecessors: dict[int, set[int]] = {}
    findings: list[Violation] = []
    for number in sorted(by_number):
        record = by_number[number]
        entries = _supersedes_entries(record)
        if entries is None:
            shape = type(_frontmatter_of(record)["supersedes"]).__name__
            detail = f"`supersedes` is a {shape}; ADR-073 defines it as a list of ADR ids"
            findings.append(Violation("supersession-target-exists", record.path, detail))
            entries = []
        targets, target_findings = _edge_targets(record, entries, "supersedes", known)
        findings.extend(target_findings)
        predecessors[number] = set(targets)

        raw = _frontmatter_of(record).get("superseded-by")
        if raw is None:
            continue
        resolved, successor_findings = _edge_targets(record, [raw], "superseded-by", known)
        findings.extend(successor_findings)
        if resolved:
            successor[number] = resolved[0]
    return _Graph(successor, predecessors, findings)


def _find_cycles(successor: dict[int, int]) -> list[list[int]]:
    """Every cycle in the ``superseded-by`` graph, each reported once.

    The graph has out-degree at most one, so a walk with a per-path index
    terminates on the first repeat. ``settled`` stops a walk from re-entering a
    node an earlier walk resolved, which bounds the scan at O(n) and is what
    keeps a cyclic corpus from hanging the gate.
    """
    settled: set[int] = set()
    cycles: list[list[int]] = []
    for start in sorted(successor):
        if start in settled:
            continue
        path: list[int] = []
        seen: dict[int, int] = {}
        node: int | None = start
        while node is not None and node not in settled:
            if node in seen:
                cycle = path[seen[node] :]
                rotate = cycle.index(min(cycle))
                cycles.append(cycle[rotate:] + cycle[:rotate])
                break
            seen[node] = len(path)
            path.append(node)
            node = successor.get(node)
        settled.update(path)
    return cycles


def _reciprocity_findings(by_number: dict[int, Record], graph: _Graph) -> list[Violation]:
    """`supersession-reciprocal` findings for both edge directions, plus cycles."""
    found: list[Violation] = []
    for number, target in sorted(graph.successor.items()):
        if number in graph.predecessors.get(target, set()):
            continue
        detail = (
            f"declares superseded-by: ADR-{target:03d}, but ADR-{target:03d} does not "
            "list it under `supersedes`"
        )
        found.append(Violation("supersession-reciprocal", by_number[number].path, detail))
    for number in sorted(graph.predecessors):
        for target in sorted(graph.predecessors[number]):
            if graph.successor.get(target) == number:
                continue
            named = graph.successor.get(target)
            actual = f"ADR-{named:03d}" if named is not None else "null"
            detail = (
                f"declares supersedes: ADR-{target:03d}, but that record's "
                f"`superseded-by` is {actual}. `superseded-by` names the immediate "
                "successor."
            )
            found.append(Violation("supersession-reciprocal", by_number[number].path, detail))
    for cycle in _find_cycles(graph.successor):
        chain = " -> ".join(f"ADR-{n:03d}" for n in [*cycle, cycle[0]])
        detail = f"`superseded-by` forms a cycle: {chain}. A supersession chain must terminate."
        found.append(Violation("supersession-reciprocal", by_number[cycle[0]].path, detail))
    return found


def _status_edge_findings(by_number: dict[int, Record], graph: _Graph) -> list[Violation]:
    """`status-edge-consistency`: `status: superseded` iff a resolved `superseded-by` edge exists.

    `supersession-reciprocal` validates `supersedes`/`superseded-by` edges
    against each other; it never checks either against the `status` enum
    (Copilot, PR #5209). Without this check a record can read
    `status: accepted` while its own `superseded-by` names a live successor
    (the generated index would list it under Accepted while the graph says
    retired), or read `status: superseded` with no successor at all (the
    index's Retired table would show `not recorded` for a reader who has no
    way to resolve it). `graph.successor` already carries only RESOLVED
    edges: an unresolved or malformed `superseded-by` is reported once, by
    `supersession-target-exists`, and does not double-report here.

    `deprecated` is deliberately outside the "superseded requires an edge"
    direction: ADR-073's schema and ADR-098's own record document
    `deprecated` for a decision that shipped and was later abandoned with no
    specific named successor, a self-deprecation rather than a supersession.

    The "superseded but no successor" direction only fires when
    `superseded-by` was never declared (``raw is None``), not merely
    unresolved: a record naming a dangling or malformed id already gets a
    `supersession-target-exists` finding for that same defect, and counting
    it again here would inflate one root cause into two check totals, the
    same containment `supersession-reciprocal` already applies against
    `supersession-target-exists` (see the module docstring).
    """
    found: list[Violation] = []
    for number in sorted(by_number):
        record = by_number[number]
        status = _status_of(record)
        target = graph.successor.get(number)
        raw = _frontmatter_of(record).get("superseded-by")
        if status == "superseded" and target is None and raw is None:
            detail = (
                "status is superseded but `superseded-by` is null; a retired "
                "record must name what replaced it"
            )
            found.append(Violation("status-edge-consistency", record.path, detail))
        elif status != "superseded" and target is not None:
            detail = (
                f"status is {status} but `superseded-by: ADR-{target:03d}` names a "
                "live successor; a record with a resolved superseded-by edge must "
                "read status: superseded"
            )
            found.append(Violation("status-edge-consistency", record.path, detail))
    return found


def scan(adr_dir: Path, repo_root: Path) -> list[Violation]:
    """Every lifecycle violation in the corpus, in check-then-path order."""
    records, violations = collect_records(adr_dir, repo_root)
    known = {record.number for record in records}
    for record in records:
        if record.frontmatter is None:
            continue
        violations.extend(_check_identity(record))
        violations.extend(_check_prose(record))
        violations.extend(_check_lifecycle_rules(record))
    by_number = {r.number: r for r in records if r.frontmatter is not None}
    graph = _build_graph(by_number, known)
    violations.extend(graph.findings)
    violations.extend(_reciprocity_findings(by_number, graph))
    violations.extend(_status_edge_findings(by_number, graph))
    return sorted(violations, key=lambda v: (CHECKS.index(v.check), v.path, v.detail))


def tally(violations: list[Violation]) -> dict[str, int]:
    """Violation count per check name; every check appears, zeros included."""
    counts = dict.fromkeys(CHECKS, 0)
    for violation in violations:
        counts[violation.check] += 1
    return counts


def read_baseline(path: Path) -> dict[str, int] | str:
    """Baseline counts, or a one-line reason the file cannot be used."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return f"baseline {path} could not be read: {exc}"
    except UnicodeDecodeError as exc:
        # Same class as _read_record above: ValueError, not OSError. A corrupt
        # baseline must degrade to the same one-line reason every other
        # unusable-baseline path returns, so the caller keeps its single
        # decision point instead of meeting a traceback.
        return f"baseline {path} is not valid UTF-8: {exc}"
    except json.JSONDecodeError as exc:
        return f"baseline {path} is not valid JSON: {exc}"
    if not isinstance(payload, dict) or not isinstance(payload.get("counts"), dict):
        return f"baseline {path} has no `counts` mapping"
    counts = payload["counts"]
    missing = sorted(set(CHECKS) - set(counts))
    unknown = sorted(set(counts) - set(CHECKS))
    if missing or unknown:
        return (
            f"baseline {path} does not match the check list (missing: "
            f"{missing or 'none'}, unknown: {unknown or 'none'}). "
            "Regenerate it with --write-baseline."
        )
    for name, value in counts.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return f"baseline {path} entry {name} is {value!r}, not a count"
    return {name: int(counts[name]) for name in CHECKS}


def write_baseline(path: Path, counts: dict[str, int]) -> None:
    """Record ``counts`` as the new ceiling. Fixed key order keeps diffs small.

    Writes through a temporary sibling file plus ``os.replace()`` rather than
    truncating ``path`` directly. Mirrors ``scripts/ai_review_common/
    cache_guard.py``'s ``_atomic_write_text`` verbatim: "Writes to a temp
    file in the same directory, then os.replace swaps it into place, so a
    crash or two concurrent writers cannot leave the file half-written or
    truncated." A direct ``path.write_text()`` interrupted mid-write (a
    killed process, a full disk) leaves invalid JSON in place, and this file
    is the ratchet ceiling every subsequent ``pre_pr.py`` run reads: a
    corrupted baseline blocks every push until someone reconstructs it by
    hand (Copilot, PR #5209 round-10 review).
    """
    payload = {
        "schema_version": "1",
        "description": _BASELINE_DESCRIPTION,
        "counts": {name: counts[name] for name in CHECKS},
    }
    text = json.dumps(payload, indent=2) + "\n"
    directory = path.parent
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _print_violations(violations: list[Violation], checks: set[str], limit: int) -> None:
    selected = [v for v in violations if v.check in checks]
    for violation in selected[:limit]:
        print(f"  - {violation.render()}")
    if len(selected) > limit:
        print(f"  ... and {len(selected) - limit} more")


def _marker(current: int, allowed: int) -> str:
    if current > allowed:
        return "RAISED"
    if current < allowed:
        return "improved, record with --write-baseline"
    return "clean, ready for zero-tolerance" if current == 0 else "at baseline"


def _report(counts: dict[str, int], baseline: dict[str, int]) -> tuple[set[str], set[str]]:
    """Print the per-check table. Returns ``(regressed, at_zero)`` check names."""
    width = max(len(name) for name in CHECKS)
    print("ADR lifecycle checks (current / baseline):")
    for name in CHECKS:
        print(
            f"  {name:<{width}}  {counts[name]:>3} / {baseline[name]:<3}  "
            f"{_marker(counts[name], baseline[name])}"
        )
    return (
        {name for name in CHECKS if counts[name] > baseline[name]},
        {name for name in CHECKS if counts[name] == 0 and baseline[name] == 0},
    )


def run(
    adr_dir: Path,
    repo_root: Path,
    baseline_path: Path,
    args: argparse.Namespace,
    *,
    repo_root_is_default: bool = False,
) -> int:
    """Scan, then either write the baseline or compare against it.

    ``repo_root_is_default`` is True only when the caller did not pass
    ``--repo-root`` explicitly (see ``main()``); it gates the worktree-identity
    check below.
    """
    violations = scan(adr_dir, repo_root)
    counts = tally(violations)
    # Read once, separately from scan()'s own collect_records() call, only for
    # the pass-report's examined-record count below: an existing but emptied
    # or narrowed corpus would otherwise print the identical
    # "[PASS] 0 violation(s)" as a completed scan of the real one (Copilot,
    # PR #5209 round-8 review). main() already rejects a fully empty corpus
    # before run() is ever called, so this count is always >= 1 here; it
    # exists to catch a narrowed-but-nonzero scope that guard cannot.
    examined = len(collect_records(adr_dir, repo_root)[0])

    if args.write_baseline:
        # .claude/rules/ci-scripts.md MUST 7: a script that resolves the
        # repository root and then writes to it must confirm the caller's cwd
        # sits inside that root before the first write. Mirrors
        # scripts/generate_third_party_notices.py:446-452 verbatim:
        #   project_root = PROJECT_ROOT
        #   if not Path.cwd().resolve().is_relative_to(project_root.resolve()):
        #       print(f"ERROR: current directory is outside project root: {Path.cwd()}", ...)
        #       return 2
        #
        # Stricter/looser/different than canonical: the canonical script's
        # PROJECT_ROOT has no CLI override, so every invocation is the risky
        # case. Here --repo-root is an explicit, user-stated argument that
        # tests deliberately point at a synthetic tmp_path corpus unrelated to
        # cwd (tests/validation/test_check_adr_lifecycle.py's `_run()` helper
        # does exactly this for every case, including
        # test_write_baseline_round_trips_and_then_passes). An explicit
        # --repo-root carries no worktree-identity risk: the caller named the
        # write target directly. The risk this check guards is narrower: the
        # *default*, which resolves via __file__ (build_parser() below), not
        # cwd, so running this script with no --repo-root override from an
        # unexpected cwd would otherwise write the baseline into that
        # __file__-derived checkout silently. So the check only fires when
        # repo_root_is_default is True.
        #
        # Re-raised (Copilot, PR #5209 round-9 review): "does not exempt
        # explicit CLI targets," reading "running from worktree A with
        # --repo-root pointing at worktree B can still overwrite B's
        # baseline" as the cross-worktree write MUST 7 exists to prevent.
        # It is not: MUST 7's own stated threat is a script's *implicit*
        # resolution being silently redirected by state the caller cannot
        # see, quoted verbatim from `.claude/rules/ci-scripts.md`: "a local
        # `core.worktree` value or a `GIT_WORK_TREE` environment variable
        # redirects it to a directory you are not standing in ... the
        # redirection is always something a person or a tool set on
        # purpose, which is exactly why a script that inherits it has no
        # way to notice." A caller-typed `--repo-root` is the opposite of
        # that: nothing is inherited or hidden, the target is exactly what
        # was written on the command line. Worktree A/B is a possible
        # *user* mistake, not an undetectable one, and no mechanism here
        # could tell a mistaken B from an intentional one without breaking
        # every test above that intentionally points --repo-root at an
        # unrelated tmp_path fixture.
        if repo_root_is_default and not Path.cwd().resolve().is_relative_to(
            repo_root.resolve()
        ):
            print(
                f"[CONFIG] current directory is outside repo root {repo_root}: "
                f"{Path.cwd()}",
                file=sys.stderr,
            )
            return EXIT_CONFIG
        write_baseline(baseline_path, counts)
        print(
            f"[OK] Wrote {baseline_path} from {len(violations)} violation(s) "
            f"across {examined} ADR record(s):"
        )
        for name in CHECKS:
            print(f"  {name}: {counts[name]}")
        return EXIT_OK

    baseline = read_baseline(baseline_path)
    if isinstance(baseline, str):
        print(f"[CONFIG] {baseline}", file=sys.stderr)
        return EXIT_CONFIG

    regressed, at_zero = _report(counts, baseline)
    if at_zero:
        print(f"Checks at zero and flippable to zero-tolerance: {', '.join(sorted(at_zero))}")
    else:
        print("No check is at zero yet; none can be flipped to zero-tolerance.")

    if args.show_all and violations:
        print(f"\nAll {len(violations)} violation(s):")
        _print_violations(violations, set(CHECKS), args.limit)

    if not regressed:
        print(
            f"\n[PASS] {len(violations)} violation(s) across {examined} ADR record(s), "
            "no check above its baseline."
        )
        return EXIT_OK

    print(f"\n[FAIL] {len(regressed)} check(s) rose above the baseline:")
    for name in sorted(regressed):
        print(f"  {name}: {baseline[name]} -> {counts[name]}")
    if not args.show_all:
        _print_violations(violations, regressed, args.limit)
    print(
        "\nFix the ADR frontmatter or prose that raised the count. Do NOT raise the "
        "baseline to clear this: the ratchet exists to stop new lifecycle drift, and "
        "raising it defeats the gate (issue #5191)."
    )
    return EXIT_REGRESSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ratcheted ADR lifecycle gate (issue #5191).")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to two levels above this script).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=f"Baseline JSON path (default: {_BASELINE_PATH.name} beside this script).",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Record the current per-check counts as the new ceiling and exit 0.",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Print every violation, not only those under a regressed check.",
    )
    parser.add_argument("--limit", type=int, default=40, help="Max violations to print.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root_is_default = args.repo_root is None
    repo_root = (
        args.repo_root if args.repo_root is not None else Path(__file__).resolve().parents[2]
    )
    adr_dir = repo_root / ".agents" / "architecture"
    if not adr_dir.is_dir():
        print(f"[CONFIG] ADR directory not found: {adr_dir}", file=sys.stderr)
        return EXIT_CONFIG
    # An emptied or misrouted corpus (wrong --repo-root, or every record moved
    # out) still passes the `is_dir()` check above. `scan()` would then walk
    # zero records, `tally()` would report every check at 0, and `run()` would
    # print "[PASS] 0 violation(s)": a missing corpus reads as a clean corpus
    # instead of failing loudly. `ADR_FILENAME_RE` excludes ADR-TEMPLATE.md, so
    # a template sitting alone does not count as evidence records were
    # examined (Copilot, PR #5209 round-7 review).
    if not any(ADR_FILENAME_RE.match(md.name) for md in adr_dir.glob("ADR-*.md")):
        print(f"[CONFIG] no ADR records found: {adr_dir}", file=sys.stderr)
        return EXIT_CONFIG
    if args.limit < 1:
        print("[CONFIG] --limit must be at least 1", file=sys.stderr)
        return EXIT_CONFIG
    return run(
        adr_dir,
        repo_root,
        args.baseline or _BASELINE_PATH,
        args,
        repo_root_is_default=repo_root_is_default,
    )


def validate_adr_lifecycle(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True when no check exceeds its baseline.

    A config error (exit 2) returns False. A gate that cannot read its own
    baseline has not run, and reporting that as a pass is the silent-pass failure
    `.claude/rules/ci-scripts.md` MUST 11 and 12 exist to stop.
    """
    return main(["--repo-root", str(repo_root)]) == EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
