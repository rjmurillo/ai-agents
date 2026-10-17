# taste-lint: ignore file-size
#
# file-size suppression rationale: this file is one test per behavior across the
# nine checks `check_adr_lifecycle.py` owns, and `.claude/rules/testing.md` MUST 1
# and the TESTING-RIGOR pos+neg+edge bar are what set its length. Its line count
# tracks how many behaviors the gate has, not how hard the module is to read;
# every test is independent and none shares state, so the rule's remediation
# (extract helpers) buys nothing. Splitting by check would scatter the six shared
# fixtures across files and force each copy to drift. Same shape and same reason
# as `tests/validation/test_check_vendor_portability.py`, which carries this
# suppression already. Issue #3779 documents the escape; issue #5191 is the work.
"""Tests for scripts/validation/check_adr_lifecycle.py (issue #5191).

Pins the ratcheted ADR lifecycle gate. Coverage per check name:

- frontmatter-parses: pos (valid block), neg (absent, malformed YAML,
  unterminated fence, non-mapping scalar), edge (a body line reading
  ``status:`` outside the frontmatter is prose and must not be parsed)
- id-matches-filename: pos, neg (absent id, wrong number), edge (``adr-7``
  and a bare integer both resolve)
- status-enum: pos, neg (``Withdrawn``, ``**PROVISIONAL**``), edge (case and
  surrounding whitespace are tolerated)
- supersession-reciprocal: pos (both sides agree), neg (one-sided in each
  direction), edge (a chain of three is reciprocal at every link, and a cycle
  is reported once instead of hanging)
- supersession-target-exists: pos, neg (self-supersession, dangling id,
  unparseable entry, non-list ``supersedes``)
- proposed-cannot-supersede: pos, neg

`implemented-implies-decided` (`implemented: true` with `status: proposed`) was
removed after Copilot review on PR #5209: ADR-073's own schema comment defines
`implemented` as flipping at first merged change regardless of decision state,
and ADR-098 documents that exact pairing as deliberate. Its three tests are
removed with it rather than left asserting a contract the gate no longer has.

- prose-frontmatter-agree: pos (decorated prose still matches), neg (drift),
  edge (inline ``**Status**:`` counts as the section; an amendment-first line
  is flagged), and the ADR-073 invariant that the gate never rewrites prose
- status-edge-consistency: pos (reciprocal superseded pair), neg (superseded
  with no edge, accepted with a resolved successor edge), edge (``deprecated``
  is exempt from the no-edge direction; a dangling ``superseded-by`` is left
  to ``supersession-target-exists`` alone, not double-counted)

- section-structure: pos (canonical set, MADR set, and a per-concept mix all pass; no
  Status or Date section is needed), neg (neither set, each concept missing alone,
  wrong heading level), edge (fenced and HTML-comment headings do not count, case and
  closing hashes are tolerated, an unparseable body is a counted finding)

- review-by-format / review-by-past-due / review-by-prose-date (issue #5193): pos (an
  absent, null, future, or on-time date passes), neg (a past date, a malformed value,
  a date missing from the prose), edge (due today is on time, the day after is late,
  quoted and unquoted YAML dates both parse, a quoted impossible date is a format
  finding, a fenced date does not count as prose, `superseded`, `deprecated`, and
  `rejected` records skip the date checks). Every case fixes "today" instead of
  reading the wall clock.

- cited-paths-exist: pos (a tracked path in Decision passes), neg (a deleted path
  fails, named in the detail), edge (a fenced illustration passes, a path outside
  Decision and Implementation Notes passes, a `deprecated` or `superseded` record
  is exempt, an unparseable body is a counted finding)

Ratchet and CLI behavior: improvement passes, regression exits 1, baseline
missing / malformed / stale exits 2, missing ADR directory exits 2,
``--write-baseline`` round-trips, and ``main(argv)`` itself returns non-zero on
a regression (``.claude/rules/ci-scripts.md`` MUST 23).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
SCRIPT = _VALIDATION_DIR / "check_adr_lifecycle.py"

if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_adr_lifecycle import (
    CHECKS,
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_REGRESSION,
    SECTION_EQUIVALENTS,
    _find_cycles,
    identities,
    main,
    scan,
    validate_adr_lifecycle,
    write_baseline,
)

# --- fixtures ---------------------------------------------------------------


def _adr_dir(tmp_path: Path) -> Path:
    path = tmp_path / ".project-toolkit" / "architecture"
    path.mkdir(parents=True)
    return path


# The canonical section set `section-structure` requires. `_write` appends it by
# default so a fixture exercising another check does not also raise this one.
_SECTIONS = "\n## Context\n\nWhy.\n\n## Decision\n\nWhat.\n\n## Consequences\n\nSo.\n"


def _write(
    adr_dir: Path,
    number: int,
    frontmatter: str | None,
    body: str = "",
    sections: str = _SECTIONS,
) -> Path:
    """Write ADR-NNN-thing.md with an optional raw frontmatter block.

    ``sections`` follows ``body`` and defaults to the canonical set; pass ``""``
    to write a record with none.
    """
    head = f"---\n{textwrap.dedent(frontmatter).strip()}\n---\n" if frontmatter else ""
    path = adr_dir / f"ADR-{number:03d}-thing.md"
    path.write_text(f"{head}\n# ADR-{number:03d}: Thing\n{body}{sections}", encoding="utf-8")
    return path


def _valid(number: int, **overrides: object) -> str:
    """A frontmatter block that satisfies every check by default."""
    fields: dict[str, object] = {
        "id": f"ADR-{number:03d}",
        "status": "accepted",
        "date": "2026-08-21",
        "supersedes": "[]",
        "superseded-by": "null",
        "implemented": "true",
    }
    fields.update(overrides)
    return "\n".join(f"{key}: {value}" for key, value in fields.items())


_STATUS_SECTION = "\n## Status\n\nAccepted (2026-08-21). Conditions were cleared in review.\n"


def _counts(tmp_path: Path) -> dict[str, int]:
    found = identities(scan(tmp_path / ".project-toolkit" / "architecture", tmp_path))
    return {name: sum(paths.values()) for name, paths in found.items()}


def _hits(tmp_path: Path, check: str) -> list[str]:
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    return [v.detail for v in scan(adr_dir, tmp_path) if v.check == check]


def _rel(number: int) -> str:
    """The record path a violation in ``_write(adr_dir, number, ...)`` carries."""
    return f".project-toolkit/architecture/ADR-{number:03d}-thing.md"


def _baseline(tmp_path: Path, **entries: dict[str, int]) -> Path:
    """A schema 2 baseline; each keyword is a check name mapped to ``{path: count}``."""
    path = tmp_path / "baseline.json"
    payload = {
        "schema_version": "2",
        "violations": {name: entries.get(name, {}) for name in CHECKS},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(repo_root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo_root), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


# --- frontmatter-parses -----------------------------------------------------


def test_valid_frontmatter_produces_no_parse_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)

    assert _counts(tmp_path)["frontmatter-parses"] == 0


def test_absent_frontmatter_is_one_violation_not_nine(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None, "\n## Status\n\nAccepted\n")

    counts = _counts(tmp_path)

    assert counts["frontmatter-parses"] == 1
    assert sum(counts.values()) == 1, "an unparseable record must not cascade"


def test_malformed_yaml_is_a_violation_not_a_crash(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, "id: ADR-001\nstatus: [unclosed\n", _STATUS_SECTION)

    details = _hits(tmp_path, "frontmatter-parses")

    assert len(details) == 1
    assert "did not parse" in details[0]


def test_an_unterminated_fence_is_not_reported_as_an_absent_one(tmp_path):
    """The record opens with `---` and carries `id`. Telling its author the block
    is absent sends them to add what is already there.

    This asserted the opposite until Copilot raised it on PR #5209.
    `_split_frontmatter` returns None for two different defects, and the message
    named only one of them. The record was always counted, so this is a wrong
    diagnosis rather than a silent drop, and the fix moves no count.
    """
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        "---\nid: ADR-001\nstatus: accepted\n\n# ADR-001\n", encoding="utf-8"
    )

    detail = _hits(tmp_path, "frontmatter-parses")

    assert len(detail) == 1
    assert "no closing `---` fence" in detail[0]
    assert "absent" not in detail[0], "the block is present, just unterminated"


def test_a_genuinely_absent_block_still_says_absent(tmp_path):
    """Negative control. Narrowing the message must not swallow the other case."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None, "\n# ADR-001\n")

    detail = _hits(tmp_path, "frontmatter-parses")

    assert len(detail) == 1
    assert detail[0] == "no leading `---` frontmatter block (ADR-073 schema absent)"


def test_an_unterminated_block_is_still_only_one_violation(tmp_path):
    """Containment holds for the new branch as it does for the old one."""
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        "---\nid: ADR-999\nstatus: nonsense\nimplemented: true\n\n## Status\n\nProposed\n",
        encoding="utf-8",
    )

    counts = _counts(tmp_path)

    assert counts["frontmatter-parses"] == 1
    assert sum(counts.values()) == 1, "an unreadable block must not cascade"


def test_non_mapping_frontmatter_is_reported_with_its_type(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, "just a scalar", _STATUS_SECTION)

    assert "not a YAML mapping" in _hits(tmp_path, "frontmatter-parses")[0]


def test_body_line_starting_status_is_prose_not_frontmatter(tmp_path):
    """Edge from the acceptance criteria: `status:` in the body is not metadata."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None, "\n## Status\n\nAccepted\n\n```yaml\nstatus: proposed\n```\n")

    counts = _counts(tmp_path)

    assert counts["frontmatter-parses"] == 1
    assert counts["status-enum"] == 0, "a body scalar must not be read as the enum"


# --- id-matches-filename ----------------------------------------------------


def test_matching_id_passes(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 7, _valid(7), _STATUS_SECTION)

    assert _counts(tmp_path)["id-matches-filename"] == 0


def test_absent_id_is_a_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 7, "status: accepted", _STATUS_SECTION)

    assert "expected ADR-007" in _hits(tmp_path, "id-matches-filename")[0]


def test_id_naming_a_different_number_is_a_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 7, _valid(7, id="ADR-008"), _STATUS_SECTION)

    assert (
        "names ADR-008 but the filename says ADR-007" in _hits(tmp_path, "id-matches-filename")[0]
    )


@pytest.mark.parametrize("raw_id", ["ADR-7", "adr-007", "ADR_7", 7])
def test_id_reference_forms_all_resolve(tmp_path, raw_id):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 7, _valid(7, id=raw_id), _STATUS_SECTION)

    assert _counts(tmp_path)["id-matches-filename"] == 0


# --- status-enum ------------------------------------------------------------


@pytest.mark.parametrize("status", ["proposed", "accepted", "rejected", "deprecated", "superseded"])
def test_every_adr073_status_is_accepted(tmp_path, status):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status=status, implemented="false"), f"\n## Status\n\n{status}\n")

    assert _counts(tmp_path)["status-enum"] == 0


@pytest.mark.parametrize("status", ["Withdrawn", '"**PROVISIONAL**"', "Accepted (conditional)"])
def test_status_outside_the_enum_is_a_violation(tmp_path, status):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status=status), _STATUS_SECTION)

    assert _counts(tmp_path)["status-enum"] == 1


def test_status_enum_owns_the_defect_and_prose_check_stays_quiet(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="Withdrawn"), _STATUS_SECTION)

    counts = _counts(tmp_path)

    assert counts["status-enum"] == 1
    assert counts["prose-frontmatter-agree"] == 0


def test_status_case_and_padding_are_tolerated(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status='"  Accepted  "'), _STATUS_SECTION)

    assert _counts(tmp_path)["status-enum"] == 0


# --- supersession -----------------------------------------------------------


def _pair(adr_dir: Path, *, old_successor: str, new_supersedes: str) -> None:
    """ADR-001 superseded by ADR-002, with each side's field supplied raw."""
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": old_successor}),
        "\n## Status\n\nSuperseded by ADR-002 (2026-08-21).\n",
    )
    _write(adr_dir, 2, _valid(2, supersedes=new_supersedes), _STATUS_SECTION)


def test_reciprocal_pair_passes(tmp_path):
    _pair(_adr_dir(tmp_path), old_successor="ADR-002", new_supersedes="[ADR-001]")

    counts = _counts(tmp_path)

    assert counts["supersession-reciprocal"] == 0
    assert counts["supersession-target-exists"] == 0


def test_successor_that_does_not_claim_the_predecessor_is_one_sided(tmp_path):
    _pair(_adr_dir(tmp_path), old_successor="ADR-002", new_supersedes="[]")

    details = _hits(tmp_path, "supersession-reciprocal")

    assert len(details) == 1
    assert "does not list it under `supersedes`" in details[0]


def test_predecessor_that_does_not_name_the_successor_is_one_sided(tmp_path):
    _pair(_adr_dir(tmp_path), old_successor="null", new_supersedes="[ADR-001]")

    details = _hits(tmp_path, "supersession-reciprocal")

    assert len(details) == 1
    assert "`superseded-by` is null" in details[0]
    assert "names the immediate successor" in details[0]


def test_transitive_superseded_by_is_rejected(tmp_path):
    """ADR-091/ADR-079 on main: 091 supersedes 079, but 079 pointed at 092."""
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-003"}),
        "\n## Status\n\nSuperseded by ADR-003.\n",
    )
    _write(
        adr_dir,
        2,
        _valid(2, status="superseded", supersedes="[ADR-001]", **{"superseded-by": "ADR-003"}),
        "\n## Status\n\nSuperseded by ADR-003.\n",
    )
    _write(adr_dir, 3, _valid(3, supersedes="[ADR-002]"), _STATUS_SECTION)

    details = _hits(tmp_path, "supersession-reciprocal")

    assert len(details) == 2
    assert any("immediate successor" in detail for detail in details)


def test_chain_of_three_is_clean_when_every_link_is_immediate(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-002"}),
        "\n## Status\n\nSuperseded by ADR-002.\n",
    )
    _write(
        adr_dir,
        2,
        _valid(2, status="superseded", supersedes="[ADR-001]", **{"superseded-by": "ADR-003"}),
        "\n## Status\n\nSuperseded by ADR-003.\n",
    )
    _write(adr_dir, 3, _valid(3, supersedes="[ADR-002]"), _STATUS_SECTION)

    assert _counts(tmp_path)["supersession-reciprocal"] == 0


def test_supersession_cycle_is_reported_once_and_terminates(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    for number, successor, predecessor in ((1, 2, 3), (2, 3, 1), (3, 1, 2)):
        _write(
            adr_dir,
            number,
            _valid(
                number,
                status="superseded",
                supersedes=f"[ADR-{predecessor:03d}]",
                **{"superseded-by": f"ADR-{successor:03d}"},
            ),
            f"\n## Status\n\nSuperseded by ADR-{successor:03d}.\n",
        )

    details = _hits(tmp_path, "supersession-reciprocal")

    assert len(details) == 1
    assert "forms a cycle: ADR-001 -> ADR-002 -> ADR-003 -> ADR-001" in details[0]


def test_find_cycles_ignores_a_terminating_chain():
    assert _find_cycles({1: 2, 2: 3}) == []


def test_find_cycles_reports_each_cycle_once_from_its_lowest_member():
    assert _find_cycles({3: 1, 1: 2, 2: 3}) == [[1, 2, 3]]


def test_self_supersession_is_a_target_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, supersedes="[ADR-001]"), _STATUS_SECTION)

    details = _hits(tmp_path, "supersession-target-exists")

    assert len(details) == 1
    assert "cannot supersede itself" in details[0]


def test_self_supersession_does_not_also_trip_reciprocity(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-001"}),
        "\n## Status\n\nSuperseded by ADR-001.\n",
    )

    counts = _counts(tmp_path)

    assert counts["supersession-target-exists"] == 1
    assert counts["supersession-reciprocal"] == 0


def test_dangling_supersession_target_is_a_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, supersedes="[ADR-404]"), _STATUS_SECTION)

    assert "which has no file" in _hits(tmp_path, "supersession-target-exists")[0]


def test_unparseable_supersession_entry_is_a_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, supersedes="[the old one]"), _STATUS_SECTION)

    assert "is not an ADR id" in _hits(tmp_path, "supersession-target-exists")[0]


def test_non_list_supersedes_mapping_is_a_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    block = "id: ADR-001\nstatus: accepted\nsupersedes:\n  why: reasons"
    _write(adr_dir, 1, block, _STATUS_SECTION)

    assert "defines it as a list of ADR ids" in _hits(tmp_path, "supersession-target-exists")[0]


def test_scalar_supersedes_is_accepted_as_a_single_entry(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-002"}),
        "\n## Status\n\nSuperseded by ADR-002.\n",
    )
    _write(adr_dir, 2, _valid(2, supersedes="ADR-001"), _STATUS_SECTION)

    counts = _counts(tmp_path)

    assert counts["supersession-target-exists"] == 0
    assert counts["supersession-reciprocal"] == 0


# --- status-edge-consistency --------------------------------------------------


def test_superseded_status_with_resolved_edge_passes(tmp_path):
    _pair(_adr_dir(tmp_path), old_successor="ADR-002", new_supersedes="[ADR-001]")

    assert _counts(tmp_path)["status-edge-consistency"] == 0


def test_superseded_status_with_no_edge_is_flagged(tmp_path):
    """`status: superseded` but `superseded-by: null`: a retired record naming no successor."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="superseded"), _STATUS_SECTION)

    details = _hits(tmp_path, "status-edge-consistency")

    assert len(details) == 1
    assert "`superseded-by` is null" in details[0]


def test_accepted_status_with_a_resolved_successor_edge_is_flagged(tmp_path):
    """`status: accepted` while `superseded-by` names a live successor: contradictory."""
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="accepted", **{"superseded-by": "ADR-002"}),
        _STATUS_SECTION,
    )
    _write(adr_dir, 2, _valid(2, supersedes="[ADR-001]"), _STATUS_SECTION)

    details = _hits(tmp_path, "status-edge-consistency")

    assert len(details) == 1
    assert "must read status: superseded" in details[0]


def test_deprecated_status_with_no_edge_is_exempt(tmp_path):
    """`deprecated` records a shipped-then-abandoned decision (ADR-098), not a supersession."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="deprecated"), _STATUS_SECTION)

    assert _counts(tmp_path)["status-edge-consistency"] == 0


def test_unresolved_superseded_by_does_not_double_report(tmp_path):
    """A dangling `superseded-by` is `supersession-target-exists`'s finding, not this check's.

    The "superseded but no successor" direction only fires when
    `superseded-by` was never declared at all (``raw is None``). A record
    naming a nonexistent id set ``superseded-by`` to something, so it is not
    silent about a successor, it named a broken one; that is
    `supersession-target-exists`'s finding to report, and this check must
    not count the same defect a second time under its own name.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-999"}),
        _STATUS_SECTION,
    )

    counts = _counts(tmp_path)

    assert counts["supersession-target-exists"] == 1
    assert counts["status-edge-consistency"] == 0


# --- cited-paths-exist ------------------------------------------------------


def _with_file(root: Path, rel: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")


def _decision(text: str) -> str:
    return f"\n## Decision\n\n{text}\n"


def test_a_live_cited_path_in_an_accepted_record_passes(tmp_path):
    _with_file(tmp_path, "scripts/live.py")
    _write(_adr_dir(tmp_path), 1, _valid(1), _decision("Run `scripts/live.py` first."))

    assert _counts(tmp_path)["cited-paths-exist"] == 0


def test_a_deleted_cited_path_in_an_accepted_record_fails(tmp_path):
    _write(_adr_dir(tmp_path), 1, _valid(1), _decision("Run `scripts/gone.py` first."))

    details = _hits(tmp_path, "cited-paths-exist")

    assert len(details) == 1
    assert "scripts/gone.py" in details[0]


def test_each_missing_path_is_its_own_violation_under_one_record(tmp_path):
    _with_file(tmp_path, "scripts/live.py")
    body = _decision("`scripts/gone_a.py`, `scripts/live.py`, and `scripts/gone_b.py`.")
    _write(_adr_dir(tmp_path), 1, _valid(1), body)

    assert _counts(tmp_path)["cited-paths-exist"] == 2


def test_a_missing_path_in_implementation_notes_fails(tmp_path):
    body = "\n## Implementation Notes\n\nSee `scripts/gone.py`.\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), body)

    assert _counts(tmp_path)["cited-paths-exist"] == 1


def test_a_missing_path_in_a_fenced_illustration_is_not_a_citation(tmp_path):
    fenced = "Shape:\n\n```yaml\npath: `scripts/illustration.py`\n```\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), _decision(fenced))

    assert _counts(tmp_path)["cited-paths-exist"] == 0


def test_a_missing_path_outside_the_binding_sections_is_not_read(tmp_path):
    body = "\n## Context\n\nOnce there was `scripts/history.py`.\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), body)

    assert _counts(tmp_path)["cited-paths-exist"] == 0


@pytest.mark.parametrize("status", ["deprecated", "rejected", "proposed"])
def test_a_record_that_is_not_accepted_is_exempt(tmp_path, status):
    _write(_adr_dir(tmp_path), 1, _valid(1, status=status), _decision("`scripts/gone.py`."))

    assert _counts(tmp_path)["cited-paths-exist"] == 0


def test_a_superseded_record_is_exempt(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-002"}),
        _decision("`scripts/gone.py`."),
    )
    _write(adr_dir, 2, _valid(2, supersedes="[ADR-001]"))

    assert _counts(tmp_path)["cited-paths-exist"] == 0


def test_a_record_without_frontmatter_is_left_to_frontmatter_parses(tmp_path):
    _write(_adr_dir(tmp_path), 1, None, _decision("`scripts/gone.py`."))

    counts = _counts(tmp_path)

    assert counts["cited-paths-exist"] == 0
    assert counts["frontmatter-parses"] == 1


def test_an_unparseable_body_is_a_finding_not_a_skip(tmp_path):
    quote = ">" * 20 + " "
    body = "\n" + quote + "```\n" + quote + "## Decision\n" + quote + "```\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), body)

    details = _hits(tmp_path, "cited-paths-exist")

    assert len(details) == 1
    assert "could not be parsed" in details[0]


def test_an_untracked_file_does_not_satisfy_a_citation_in_a_git_checkout(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    _with_file(tmp_path, "scripts/residue.py")
    _write(_adr_dir(tmp_path), 1, _valid(1), _decision("`scripts/residue.py`."))

    assert _counts(tmp_path)["cited-paths-exist"] == 1


# --- section-structure ------------------------------------------------------

_MADR_SECTIONS = (
    "\n## Context and Problem Statement\n\nWhy.\n\n## Considered Options\n\nA, B.\n\n"
    "## Decision Outcome\n\nA.\n\n### Consequences\n\nSo.\n"
)


def test_the_canonical_heading_set_passes(tmp_path):
    _write(_adr_dir(tmp_path), 1, _valid(1))

    assert _counts(tmp_path)["section-structure"] == 0


def test_the_madr_heading_set_passes(tmp_path):
    _write(_adr_dir(tmp_path), 1, _valid(1), sections=_MADR_SECTIONS)

    assert _counts(tmp_path)["section-structure"] == 0


def test_a_per_concept_mix_of_the_two_sets_passes(tmp_path):
    sections = "\n## Context\n\nWhy.\n\n## Decision Outcome\n\nA.\n\n## Consequences\n\nSo.\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), sections=sections)

    assert _counts(tmp_path)["section-structure"] == 0


def test_status_and_date_sections_are_not_required(tmp_path):
    """ADR-073 (amended 2026-09-29) made `## Status` optional; `## Date` restates frontmatter."""
    _write(_adr_dir(tmp_path), 1, _valid(1))

    counts = _counts(tmp_path)

    assert counts["section-structure"] == 0
    assert counts["prose-frontmatter-agree"] == 0


def test_a_record_matching_neither_set_names_every_missing_concept(tmp_path):
    _write(_adr_dir(tmp_path), 1, _valid(1), sections="\n## Background\n\nWords.\n")

    details = _hits(tmp_path, "section-structure")

    assert len(details) == 1
    assert "missing Context, Decision, Consequences" in details[0]
    assert "ADR-TEMPLATE.md" in details[0]


@pytest.mark.parametrize(
    ("kept", "missing"),
    [
        ("## Decision\n\nD.\n\n## Consequences\n\nC.\n", "Context"),
        ("## Context\n\nW.\n\n## Consequences\n\nC.\n", "Decision"),
        ("## Context\n\nW.\n\n## Decision\n\nD.\n", "Consequences"),
    ],
)
def test_each_missing_concept_is_named_alone(tmp_path, kept, missing):
    _write(_adr_dir(tmp_path), 1, _valid(1), sections="\n" + kept)

    details = _hits(tmp_path, "section-structure")

    assert len(details) == 1
    assert details[0].startswith(f"missing {missing}.")


def test_a_context_heading_at_level_three_does_not_count(tmp_path):
    sections = "\n### Context\n\nW.\n\n## Decision\n\nD.\n\n## Consequences\n\nC.\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), sections=sections)

    assert _hits(tmp_path, "section-structure")[0].startswith("missing Context.")


def test_a_consequences_heading_at_level_four_does_not_count(tmp_path):
    sections = "\n## Context\n\nW.\n\n## Decision\n\nD.\n\n#### Consequences\n\nC.\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), sections=sections)

    assert _hits(tmp_path, "section-structure")[0].startswith("missing Consequences.")


def test_headings_in_a_fence_or_html_comment_do_not_count(tmp_path):
    sections = "\n```markdown\n## Context\n\n## Decision\n\n```\n\n<!--\n## Consequences\n-->\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), sections=sections)

    assert "missing Context, Decision, Consequences" in _hits(tmp_path, "section-structure")[0]


def test_heading_case_and_closing_hashes_are_tolerated(tmp_path):
    sections = "\n## CONTEXT ##\n\nW.\n\n## decision outcome\n\nD.\n\n## Consequences\n\nC.\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), sections=sections)

    assert _counts(tmp_path)["section-structure"] == 0


def test_a_record_without_frontmatter_is_left_to_frontmatter_parses_for_structure(tmp_path):
    _write(_adr_dir(tmp_path), 1, None, sections="")

    counts = _counts(tmp_path)

    assert counts["section-structure"] == 0
    assert counts["frontmatter-parses"] == 1


def test_an_unparseable_body_is_a_structure_finding_not_a_skip(tmp_path):
    quote = ">" * 20 + " "
    body = "\n" + quote + "```\n" + quote + "## Decision\n" + quote + "```\n"
    _write(_adr_dir(tmp_path), 1, _valid(1), body)

    details = _hits(tmp_path, "section-structure")

    assert len(details) == 1
    assert "could not be parsed" in details[0]


def test_the_mapping_and_the_template_agree():
    """ADR-TEMPLATE.md documents every heading the gate accepts."""
    template = (REPO_ROOT / ".project-toolkit" / "architecture" / "ADR-TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    for concept, names, _levels in SECTION_EQUIVALENTS:
        assert concept in template
        for name in names:
            assert name in template.lower(), f"{name!r} is accepted by the gate but undocumented"


# --- proposed-cannot-supersede / implemented-implies-decided ----------------


def test_accepted_record_may_supersede(tmp_path):
    _pair(_adr_dir(tmp_path), old_successor="ADR-002", new_supersedes="[ADR-001]")

    assert _counts(tmp_path)["proposed-cannot-supersede"] == 0


def test_proposed_record_may_not_supersede(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-002"}),
        "\n## Status\n\nSuperseded by ADR-002.\n",
    )
    _write(
        adr_dir,
        2,
        _valid(2, status="proposed", supersedes="[ADR-001]", implemented="false"),
        "\n## Status\n\nProposed.\n",
    )

    assert _counts(tmp_path)["proposed-cannot-supersede"] == 1


# --- prose-frontmatter-agree ------------------------------------------------


@pytest.mark.parametrize(
    "prose",
    [
        "Accepted (amended 2026-07-19: narrowed to hooks).",
        "`Accepted`. Supersedes nothing.",
        "> Accepted by repo-owner authorization.",
        "Accepted 2026-06-19 by repo-owner authorization, bound to the debate log.",
    ],
)
def test_prose_with_nuance_matching_the_enum_passes(tmp_path, prose):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), f"\n## Status\n\n{prose}\n")

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


@pytest.mark.parametrize(
    "prose",
    [
        "Accepted",
        "**Accepted**",
        "accepted",
        "Accepted.",
        "`Accepted`",
        "Accepted (2026-06-19)",
        "Accepted 2026-06-19.",
    ],
)
def test_a_bare_restatement_of_the_enum_is_forbidden(tmp_path, prose):
    """ADR-073 amendment 2026-09-29: a `## Status` that only says the enum word."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), f"\n## Status\n\n{prose}\n")

    details = _hits(tmp_path, "prose-frontmatter-agree")

    assert len(details) == 1
    assert "only restates frontmatter status: accepted" in details[0]


def test_a_very_long_status_line_is_nuance_and_is_not_scanned_slowly(tmp_path):
    """Edge: a 32k-space run must neither hang the gate nor read as a restatement."""
    adr_dir = _adr_dir(tmp_path)
    line = "Accepted" + " " * 32000 + "x"
    _write(adr_dir, 1, _valid(1), f"\n## Status\n\n{line}\n")

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


@pytest.mark.parametrize(
    "prose",
    [
        "Superseded by ADR-042",
        "Superseded by [ADR-042](ADR-042.md)",
        "Superseded by ADR-042 on 2026-08-19",
        "Superseded by ADR-042 (2026-08-19)",
        "Superseded by ADR-042 2026-08-19.",
        "Superseded on 2026-08-19",
        "Superseded (2026-08-19) by ADR-042",
    ],
)
def test_superseded_restatement_forms_are_forbidden(tmp_path, prose):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="superseded"), f"\n## Status\n\n{prose}\n")

    assert len(_hits(tmp_path, "prose-frontmatter-agree")) == 1


@pytest.mark.parametrize(
    "prose",
    [
        "Accepted on 2026-08-19",
        "Accepted (2026-08-19)",
        "Accepted on 2026-08-19.",
    ],
)
def test_dated_accepted_restatement_forms_are_forbidden(tmp_path, prose):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), f"\n## Status\n\n{prose}\n")

    assert len(_hits(tmp_path, "prose-frontmatter-agree")) == 1


@pytest.mark.parametrize(
    ("status", "prose"),
    [
        ("accepted", "Accepted by ADR-042"),
        ("accepted", "Accepted by [ADR-042](ADR-042.md)"),
        ("proposed", "Proposed by ADR-042 on 2026-08-19"),
        ("superseded", "Superseded by ADR-042 on 2026-08-19 (2026-08-20)"),
        ("superseded", "Superseded by ADR-042 because it broke hooks"),
        ("accepted", "Accepted on 2026-08-19 after the P1 findings cleared"),
    ],
)
def test_forms_that_say_more_than_the_enum_are_not_restatements(tmp_path, status, prose):
    """Negative: a successor on a non-superseded record, two dates, or trailing nuance."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status=status), f"\n## Status\n\n{prose}\n")

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_a_superseded_restatement_naming_the_successor_is_forbidden(tmp_path):
    """The ADR-005 shape the owner called duplicative: enum plus superseded-by."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="superseded"), "\n## Status\n\nSuperseded by ADR-042\n")

    assert len(_hits(tmp_path, "prose-frontmatter-agree")) == 1


def test_a_multi_line_status_section_is_nuance_not_restatement(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Status\n\nAccepted\n\nConditions: clear the two P1 findings first.\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_a_drifting_bare_word_is_one_violation_not_two(tmp_path):
    """Drift wins: the restatement check runs only after the words agree."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="superseded"), "\n## Status\n\nAccepted\n")

    details = _hits(tmp_path, "prose-frontmatter-agree")

    assert len(details) == 1
    assert "Frontmatter wins" in details[0]


def test_a_fenced_status_sample_is_not_read_as_a_restatement(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n```markdown\n## Status\n\nAccepted\n```\n")

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_a_status_section_followed_by_another_section_is_still_bounded(tmp_path):
    """The section ends at the next level-2 heading, so later prose is not its body."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n## Status\n\nAccepted\n\n## Context\n\nWords.\n")

    assert len(_hits(tmp_path, "prose-frontmatter-agree")) == 1


def test_prose_naming_a_different_lifecycle_word_is_drift(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="superseded"), "\n## Status\n\nAccepted (2026-01-01).\n")

    details = _hits(tmp_path, "prose-frontmatter-agree")

    assert len(details) == 1
    assert "Frontmatter wins" in details[0]


def test_prose_opening_with_an_amendment_is_drift(tmp_path):
    """ADR-068 on main: the section opens with `**Amended ...**`, not a status."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n## Status\n\n**Amended 2026-08-19 (ADR-097):** retired.\n")

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1


def test_inline_bold_status_counts_as_the_section(tmp_path):
    """ADR-055's format: `**Status**: Accepted (supersedes ADR-024, ADR-025)`."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n**Status**: Accepted (supersedes ADR-024, ADR-025)\n")

    counts = _counts(tmp_path)

    assert counts["prose-frontmatter-agree"] == 0


def test_status_heading_is_matched_case_insensitively(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n### STATUS\n\nAccepted\n")

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_absent_status_prose_is_not_a_violation(tmp_path):
    """A record whose frontmatter fully states its status owes no prose restatement.

    The repo owner rejected the opposite rule on review of ADR-005: with
    `status: superseded` and `superseded-by: ADR-042` in frontmatter, a prose line
    reading "Superseded by ADR-042" is duplication, not a reader service. ADR-073
    agrees since its 2026-09-29 amendment: the section is optional.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n## Context\n\nWords.\n")

    counts = _counts(tmp_path)

    assert counts["prose-frontmatter-agree"] == 0
    assert "status-section-present" not in counts


def test_unparseable_markdown_is_a_violation_not_a_silent_skip(tmp_path):
    """A body that defeats the markdown parser is reported, not exempted.

    `blank_non_prose_block_lines` raises `MarkdownNestingError` when a document
    nests past the parser's limit (`scripts/utils/markdown_parser.py`,
    `_blank_block_lines`, "Any exception the parser raises propagates to the
    caller, which must not treat a parse failure as clean prose").
    `_status_prose` used to catch that exception and return `None`, which
    reads as "no status section" to `_check_prose` and silently exempts the
    record from `prose-frontmatter-agree`. Fixed to catch it in `_check_prose`
    instead and report a violation. Copilot found this on PR #5209.
    """
    depth = 20
    quote = ">" * depth + " "
    unparseable_body = (
        "\n"
        + quote
        + "```\n"
        + quote
        + "## Status\n"
        + quote
        + "```\n"
        + "\n## Status\n\nAccepted\n"
    )
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), unparseable_body)

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1


def test_empty_status_section_still_drifts(tmp_path):
    """Prose that opens the section and then says nothing is still a disagreement.

    Absence is fine; a section that exists and contradicts the enum is not.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n## Status\n")

    counts = _counts(tmp_path)

    assert counts["prose-frontmatter-agree"] == 1


def test_gate_never_mutates_an_adr(tmp_path):
    """ADR-073: "the gate never silently rewrites prose"."""
    adr_dir = _adr_dir(tmp_path)
    path = _write(adr_dir, 1, _valid(1, status="superseded"), "\n## Status\n\nAccepted\n")
    before = path.read_bytes()

    _run(tmp_path, "--baseline", str(_baseline(tmp_path)), "--show-all")

    assert path.read_bytes() == before


# --- ratchet and CLI --------------------------------------------------------


def test_counts_at_baseline_exit_zero(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 1}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "[PASS]" in result.stdout


def test_pass_report_names_the_examined_record_count(tmp_path):
    """A clean pass must be distinguishable from an idle run over no records.

    Without the count, a narrowed corpus (a path bug that only reaches a
    handful of the real ADRs) prints the identical "[PASS] 0 violation(s)"
    as a completed scan of the whole corpus (Copilot, PR #5209 round-8
    review).
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    _write(adr_dir, 2, _valid(2), _STATUS_SECTION)
    baseline = _baseline(tmp_path)

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "[PASS] 0 violation(s) across 2 ADR record(s)" in result.stdout


def test_a_risen_count_fails_and_names_the_check(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    _write(adr_dir, 2, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 1}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_REGRESSION
    assert "frontmatter-parses: 1 -> 2" in result.stdout
    assert "Do NOT raise the baseline" in result.stdout


def test_an_improvement_passes_without_rewriting_the_baseline(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 5}})
    before = baseline.read_text(encoding="utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_OK
    assert "improved, record with --write-baseline" in result.stdout
    assert baseline.read_text(encoding="utf-8") == before


def test_swapping_a_violation_to_another_record_fails(tmp_path):
    """Issue #5273: fix ADR-001, break ADR-002; the check total stays at 1."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    _write(adr_dir, 2, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 1}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_REGRESSION, result.stdout + result.stderr
    assert "frontmatter-parses: 1 -> 1" in result.stdout
    assert "SWAPPED" in result.stdout
    assert _rel(2) in result.stdout
    assert "Fixing a different record does not offset it" in result.stdout


def test_a_new_violation_fails_even_when_the_check_total_fell(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 3, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 2}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_REGRESSION, result.stdout + result.stderr
    assert "frontmatter-parses: 2 -> 1" in result.stdout


def test_a_pure_fix_passes_and_is_reported_as_an_improvement(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    _write(adr_dir, 2, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 1, _rel(2): 1}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "improved, record with --write-baseline" in result.stdout


def test_a_second_violation_of_one_check_in_a_recorded_record_fails(tmp_path):
    """The key carries a count, so one record cannot absorb a second violation."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, supersedes="[ADR-090, ADR-091]"), _STATUS_SECTION)
    baseline = _baseline(tmp_path, **{"supersession-target-exists": {_rel(1): 1}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_REGRESSION, result.stdout + result.stderr
    assert "supersession-target-exists: 1 -> 2" in result.stdout


def test_a_swap_across_checks_in_one_record_fails(tmp_path):
    """A record recorded under one check does not excuse a different check."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status="bogus"), _STATUS_SECTION)
    baseline = _baseline(tmp_path, **{"id-matches-filename": {_rel(1): 1}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_REGRESSION, result.stdout + result.stderr
    assert "status-enum: 0 -> 1" in result.stdout


def test_write_baseline_after_a_fix_records_only_what_remains(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    _write(adr_dir, 2, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 1, _rel(2): 1}})

    written = _run(tmp_path, "--baseline", str(baseline), "--write-baseline")

    assert written.returncode == EXIT_OK, written.stdout + written.stderr
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    assert payload["violations"]["frontmatter-parses"] == {_rel(2): 1}


def test_run_reports_which_checks_are_ready_for_zero_tolerance(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 1}})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert "Checks at zero and flippable to zero-tolerance:" in result.stdout
    assert "status-enum" in result.stdout


def test_write_baseline_round_trips_and_then_passes(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    _write(
        adr_dir,
        2,
        _valid(2, status="proposed", supersedes="[ADR-001]"),
        "\n## Status\n\nProposed\n",
    )
    baseline = tmp_path / "baseline.json"

    written = _run(tmp_path, "--baseline", str(baseline), "--write-baseline")

    assert written.returncode == EXIT_OK
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2"
    assert payload["violations"]["frontmatter-parses"] == {_rel(1): 1}
    assert payload["violations"]["proposed-cannot-supersede"] == {_rel(2): 1}
    assert list(payload["violations"]) == list(CHECKS)
    assert _run(tmp_path, "--baseline", str(baseline)).returncode == EXIT_OK


def test_write_baseline_leaves_no_temp_file_behind(tmp_path):
    """A successful write cleans up its own temp file.

    ``write_baseline()`` writes through a ``tempfile.mkstemp()`` sibling and
    ``os.replace()``; the temp name must not survive a successful call, or
    every ``--write-baseline`` invocation would leak one file (Copilot,
    PR #5209 round-10 review, "baseline writes are not atomic as documented").
    """
    baseline = tmp_path / "baseline.json"

    write_baseline(baseline, {name: {} for name in CHECKS})

    assert baseline.exists()
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_baseline_preserves_the_old_file_when_replace_fails(tmp_path, monkeypatch):
    """A failed swap must not corrupt or half-write the existing baseline.

    Simulates the crash-mid-write scenario the atomic-write fix closes:
    ``os.replace()`` raising leaves the pre-existing baseline content
    untouched (the temp file was fully written first, then discarded) rather
    than a partially-written or truncated file.
    """
    baseline = tmp_path / "baseline.json"
    original = '{"schema_version": "1", "counts": {}}'
    baseline.write_text(original, encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        write_baseline(baseline, {name: {} for name in CHECKS})

    assert baseline.read_text(encoding="utf-8") == original
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_baseline_names_the_examined_record_count(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    _write(adr_dir, 2, _valid(2), _STATUS_SECTION)
    baseline = tmp_path / "baseline.json"

    result = _run(tmp_path, "--baseline", str(baseline), "--write-baseline")

    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "[OK] Wrote" in result.stdout
    assert "across 2 ADR record(s)" in result.stdout


# --- worktree-identity guard (.claude/rules/ci-scripts.md MUST 7) -----------
#
# --repo-root defaults to a path derived from __file__ (build_parser()), not
# from cwd. The guard in run() only fires for that default: every other
# --write-baseline test in this file passes --repo-root explicitly (pointing
# at a synthetic tmp_path corpus unrelated to cwd, by design), and an explicit
# --repo-root is a stated write target that carries no worktree-identity risk.


def test_write_baseline_with_default_repo_root_succeeds_when_cwd_is_inside_it(
    tmp_path, monkeypatch
):
    baseline = tmp_path / "baseline.json"
    monkeypatch.chdir(REPO_ROOT)

    exit_code = main(["--baseline", str(baseline), "--write-baseline"])

    assert exit_code == EXIT_OK
    assert baseline.exists()


def test_write_baseline_with_default_repo_root_rejects_a_cwd_outside_it(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--baseline", str(baseline), "--write-baseline"])

    assert exit_code == EXIT_CONFIG
    assert not baseline.exists()


def test_write_baseline_with_explicit_repo_root_ignores_cwd(tmp_path, monkeypatch):
    """An explicit --repo-root is a stated write target; the guard does not apply
    even when cwd sits outside it entirely.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = tmp_path / "baseline.json"
    monkeypatch.chdir(tmp_path.parent)

    exit_code = main(
        ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--write-baseline"]
    )

    assert exit_code == EXIT_OK
    assert baseline.exists()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_write_baseline_refuses_to_raise_a_check_above_the_base_ref(tmp_path):
    """A branch must not launder a raised count through --write-baseline: the
    recorded ceiling may only fall (issue #5191, Copilot PR #5209 round-11
    review: "--write-baseline writes the current counts and exits 0 before
    reading either the existing baseline or its value at the base ref...
    Compare every proposed count with the baseline at the base ref ... and
    reject any increase.").
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    baseline = tmp_path / "baseline.json"
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")

    # Base ref: a clean corpus, baseline committed recording zero everywhere.
    write_args = ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--write-baseline"]
    assert main(write_args) == EXIT_OK
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base: clean corpus, baseline at zero")

    # Working tree regresses without a new commit: a malformed-frontmatter
    # record raises frontmatter-parses from 0 to 1.
    _write(adr_dir, 2, "id: ADR-002\nstatus: [unclosed\n", _STATUS_SECTION)

    exit_code = main(write_args)

    assert exit_code == EXIT_CONFIG
    # The on-disk baseline is untouched: the refused write never ran.
    assert (
        json.loads(baseline.read_text(encoding="utf-8"))["violations"]["frontmatter-parses"] == {}
    )


def test_write_baseline_allows_bootstrap_when_base_ref_has_no_baseline(tmp_path):
    """The commit that introduces this gate's baseline has no earlier value at
    the base ref to compare against; --write-baseline must still succeed
    (bootstrap), matching the finding's own "allow bootstrap only when that
    ref has no baseline" requirement.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base: no baseline file committed yet")

    baseline = tmp_path / "baseline.json"  # absent at HEAD; never committed

    exit_code = main(
        ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--write-baseline"]
    )

    assert exit_code == EXIT_OK
    assert baseline.exists()


def test_write_baseline_ignores_base_ref_when_the_baseline_path_is_outside_repo_root(tmp_path):
    """A `--baseline` path outside `--repo-root` (legal: they are independent
    flags, see test_write_baseline_with_default_repo_root_succeeds_when_cwd_is_inside_it,
    which points --baseline at a bare tmp_path file while --repo-root defaults
    to the real checkout) has no tracked history in that repo to compare
    against. `git show`/`git ls-tree` against an out-of-repo pathspec fails
    outright rather than reporting "absent", so this must be skipped before
    asking git anything, not surfaced as a false [CONFIG] failure.
    """
    repo_root = tmp_path / "repo"
    adr_dir = _adr_dir(repo_root)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    _git(repo_root, "init", "-q", "-b", "main")
    _git(repo_root, "config", "user.email", "t@example.com")
    _git(repo_root, "config", "user.name", "t")
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", "base")

    outside_baseline = tmp_path / "elsewhere" / "baseline.json"
    outside_baseline.parent.mkdir()

    exit_code = main(
        ["--repo-root", str(repo_root), "--baseline", str(outside_baseline), "--write-baseline"]
    )

    assert exit_code == EXIT_OK
    assert outside_baseline.exists()


def test_missing_baseline_is_a_config_error(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)

    result = _run(tmp_path, "--baseline", str(tmp_path / "absent.json"))

    assert result.returncode == EXIT_CONFIG
    assert "could not be read" in result.stderr


def test_malformed_baseline_is_a_config_error(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{not json", encoding="utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_CONFIG
    assert "not valid JSON" in result.stderr


def test_baseline_missing_a_check_is_a_config_error(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"violations": {"status-enum": {}}}), encoding="utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_CONFIG
    assert "does not match the check list" in result.stderr


def test_baseline_with_a_non_count_value_is_a_config_error(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    baseline = tmp_path / "baseline.json"
    entries: dict[str, dict[str, int]] = {name: {} for name in CHECKS}
    entries["status-enum"] = {_rel(1): -1}
    baseline.write_text(json.dumps({"violations": entries}), encoding="utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_CONFIG
    assert "not a count" in result.stderr


def test_missing_adr_directory_is_a_config_error(tmp_path):
    result = _run(tmp_path)

    assert result.returncode == EXIT_CONFIG
    assert "ADR directory not found" in result.stderr


def test_non_adr_files_in_the_directory_are_ignored(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-TEMPLATE.md").write_text("# Template\n", encoding="utf-8")
    (adr_dir / "DESIGN-REVIEW-thing.md").write_text("# Review\n", encoding="utf-8")
    (adr_dir / "README.md").write_text("# Readme\n", encoding="utf-8")

    assert sum(_counts(tmp_path).values()) == 0


def test_an_empty_adr_directory_is_a_config_error(tmp_path):
    """An emptied directory must fail loudly, not report a clean scan.

    ``scan()`` on zero records returns zero violations (see
    ``test_non_adr_files_in_the_directory_are_ignored`` above), and without a
    CLI-level guard that reads as "[PASS] 0 violation(s)": a wrong
    ``--repo-root`` or a corpus emptied by accident looks identical to a
    genuinely clean one (Copilot, PR #5209 round-7 review).
    """
    _adr_dir(tmp_path)

    result = _run(tmp_path)

    assert result.returncode == EXIT_CONFIG
    assert "no ADR records found" in result.stderr


def test_an_adr_directory_with_only_a_template_is_a_config_error(tmp_path):
    """``ADR-TEMPLATE.md`` alone must not count as evidence records exist."""
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-TEMPLATE.md").write_text("# Template\n", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode == EXIT_CONFIG
    assert "no ADR records found" in result.stderr


def test_main_returns_nonzero_on_a_regression(tmp_path):
    """CLI exit contract: the process, not just a helper, must report failure."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = _baseline(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == EXIT_REGRESSION


def test_main_returns_config_code_on_a_bad_limit(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)

    assert main(["--repo-root", str(tmp_path), "--limit", "0"]) == EXIT_CONFIG


def test_pre_pr_adapter_reports_false_when_the_gate_fails(tmp_path, monkeypatch):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    monkeypatch.setattr("check_adr_lifecycle._BASELINE_PATH", _baseline(tmp_path))

    assert validate_adr_lifecycle(tmp_path) is False


def test_pre_pr_adapter_reports_true_when_the_gate_passes(tmp_path, monkeypatch):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    monkeypatch.setattr("check_adr_lifecycle._BASELINE_PATH", _baseline(tmp_path))

    assert validate_adr_lifecycle(tmp_path) is True


def test_pre_pr_adapter_reports_false_on_a_config_error(tmp_path, monkeypatch):
    """A gate that cannot read its baseline has not run; it must not report PASS."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    monkeypatch.setattr("check_adr_lifecycle._BASELINE_PATH", tmp_path / "absent.json")

    assert validate_adr_lifecycle(tmp_path) is False


# --- the shipped baseline ---------------------------------------------------


def test_the_shipped_baseline_covers_every_check():
    payload = json.loads(
        (_VALIDATION_DIR / "adr_lifecycle_baseline.json").read_text(encoding="utf-8")
    )

    assert payload["schema_version"] == "2"
    assert list(payload["violations"]) == list(CHECKS)
    assert all(
        isinstance(count, int) and count >= 1
        for paths in payload["violations"].values()
        for count in paths.values()
    )


def test_the_repository_corpus_does_not_exceed_the_shipped_baseline(monkeypatch):
    """ci-scripts.md MUST 13: the gate must pass against the full corpus.

    "Today" is pinned: the review-by past-due check reads the clock, and an
    unpinned run would go red on the day any real ADR's review-by date passes,
    for every unrelated PR. The pre_pr gate stays the forcing function.
    """
    monkeypatch.setattr("check_adr_lifecycle._utc_today", lambda: _TODAY)

    assert main(["--repo-root", str(REPO_ROOT)]) == EXIT_OK


# --- in-process coverage of paths the subprocess tests shadow ---------------


def test_empty_frontmatter_block_names_itself(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text("---\n\n---\n\n# ADR-001\n", encoding="utf-8")

    assert _hits(tmp_path, "frontmatter-parses") == ["frontmatter block is empty"]


def test_non_scalar_status_is_reported_by_the_enum_check(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, "id: ADR-001\nstatus:\n  - accepted", _STATUS_SECTION)

    assert _counts(tmp_path)["status-enum"] == 1


def test_list_valued_superseded_by_is_not_an_adr_id(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    block = "id: ADR-001\nstatus: accepted\nsuperseded-by:\n  - ADR-002"
    _write(adr_dir, 1, block, _STATUS_SECTION)

    assert "is not an ADR id" in _hits(tmp_path, "supersession-target-exists")[0]


def test_frontmatter_accessor_refuses_an_unparsed_record():
    from check_adr_lifecycle import Record, _frontmatter_of

    with pytest.raises(ValueError, match="no parsed frontmatter"):
        _frontmatter_of(Record(1, "ADR-001-thing.md", None, ""))


def test_limit_truncates_the_printed_violation_list(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    for number in range(1, 6):
        _write(adr_dir, number, None)
    baseline = _baseline(tmp_path)

    result = _run(tmp_path, "--baseline", str(baseline), "--limit", "2")

    assert result.returncode == EXIT_REGRESSION
    assert "... and 3 more" in result.stdout


def test_show_all_prints_violations_under_clean_checks_too(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": {_rel(1): 1}})

    result = _run(tmp_path, "--baseline", str(baseline), "--show-all")

    assert result.returncode == EXIT_OK
    assert "All 1 violation(s):" in result.stdout


def test_read_baseline_rejects_a_payload_without_counts(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"schema_version": "2"}), encoding="utf-8")

    assert "has no `violations` mapping" in read_baseline(path)


def test_read_baseline_rejects_a_schema_1_counts_file(tmp_path):
    """Schema 1 cannot name the records behind a count; regenerate instead."""
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"schema_version": "1", "counts": dict.fromkeys(CHECKS, 0)}), encoding="utf-8"
    )

    reason = read_baseline(path)

    assert isinstance(reason, str)
    assert "schema 1" in reason
    assert "--write-baseline" in reason


def test_read_baseline_rejects_a_non_mapping_check_entry(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    entries: dict[str, object] = {name: {} for name in CHECKS}
    entries["status-enum"] = 3
    path.write_text(json.dumps({"violations": entries}), encoding="utf-8")

    assert "not a mapping of path to count" in read_baseline(path)


def test_read_baseline_rejects_an_empty_path_key(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    entries: dict[str, dict[str, int]] = {name: {} for name in CHECKS}
    entries["status-enum"] = {"": 1}
    path.write_text(json.dumps({"violations": entries}), encoding="utf-8")

    assert "not a record path" in read_baseline(path)


def test_read_baseline_rejects_a_zero_count_entry(tmp_path):
    """An entry at zero is noise: omit the path instead."""
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    entries: dict[str, dict[str, int]] = {name: {} for name in CHECKS}
    entries["status-enum"] = {_rel(1): 0}
    path.write_text(json.dumps({"violations": entries}), encoding="utf-8")

    assert "not a count" in read_baseline(path)


def test_read_baseline_accepts_a_well_formed_schema_2_file(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = _baseline(tmp_path, **{"status-enum": {_rel(1): 2}})

    parsed = read_baseline(path)

    assert isinstance(parsed, dict)
    assert parsed["status-enum"] == {_rel(1): 2}
    assert parsed["frontmatter-parses"] == {}


def test_read_baseline_rejects_an_unknown_check_name(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    entries: dict[str, dict[str, int]] = {name: {} for name in CHECKS}
    entries["retired-check"] = {}
    path.write_text(json.dumps({"violations": entries}), encoding="utf-8")

    assert "unknown: ['retired-check']" in read_baseline(path)


def test_read_baseline_rejects_a_boolean_count(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    entries: dict[str, dict[str, object]] = {name: {} for name in CHECKS}
    entries["status-enum"] = {_rel(1): True}
    path.write_text(json.dumps({"violations": entries}), encoding="utf-8")

    assert "not a count" in read_baseline(path)


def test_main_write_baseline_then_pass_in_process(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = tmp_path / "baseline.json"

    argv = ["--repo-root", str(tmp_path), "--baseline", str(baseline)]
    assert main([*argv, "--write-baseline"]) == EXIT_OK
    assert main(argv) == EXIT_OK


def test_main_reports_config_error_for_a_missing_directory_in_process(tmp_path):
    assert main(["--repo-root", str(tmp_path)]) == EXIT_CONFIG


def test_main_reports_no_check_ready_when_every_check_has_debt(tmp_path, capsys):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = _baseline(tmp_path, **{name: {_rel(1): 1} for name in CHECKS})

    assert main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == EXIT_OK
    assert "No check is at zero yet" in capsys.readouterr().out


def test_level_three_status_subsection_is_not_the_record_status(tmp_path):
    """A `### Status` deep in the body belongs to a subsection, not the record.

    Real case: ADR-042 carries `### Status` at line 171 inside a migration-phase
    section. While a real `## Status` sat higher in the file the deeper heading was
    masked; removing the redundant top section surfaced it and the gate read
    "Proposed" as the record's lifecycle status against `status: accepted`.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Acceptance Evidence\n\nRatified in PR #963.\n"
        "\n## Migration Phases\n\n### Phase 1\n\n### Status\n\nProposed\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_inline_status_label_deep_in_body_is_not_the_record_status(tmp_path):
    """`**Status**:` under a phase or exception heading is that thing's status.

    Real case: ADR-055 carries `**Status**: COMPLETE` at line 119 (a migration
    phase result) and `**Status**: APPROVED` at line 168 (an exception ruling).
    Neither describes the record's lifecycle.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Provenance\n\nRenumbered by PR #1604.\n"
        "\n## Migration\n\n**Status**: COMPLETE (2025-12-29)\n"
        "\n## Exceptions\n\n**Status**: APPROVED\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_record_status_is_still_found_when_it_is_the_first_section(tmp_path):
    """Positive control: scoping must not stop the gate seeing a real drift."""
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Status\n\nProposed\n\n## Context\n\nWords.\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1


def test_a_status_section_after_another_section_is_still_checked(tmp_path):
    """Section order must not decide whether the drift check runs.

    This asserted the opposite until Copilot found it on PR #5209. An earlier
    revision bounded the search to the record header, so a `## Status` placed
    after `## Context` was invisible and moving the section silently bypassed
    `prose-frontmatter-agree`. Nothing in ADR-073 or issue #5191 constrains
    section order, so nothing justified treating position as authority.

    The fixture's frontmatter says `accepted` and its prose says `Proposed`.
    That is drift, and it must be reported wherever the section sits.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Context\n\nWords.\n\n## Status\n\nProposed\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1


def test_a_level_three_status_subsection_is_not_the_records_status(tmp_path):
    """`### Status` belongs to whatever contains it, never to the record.

    ADR-042 carries one at line 171 reading "Proposed" inside a migration phase
    while its frontmatter says `accepted`. Matching it manufactured a drift
    violation out of a correct record.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Context\n\nWords.\n\n### Status\n\nProposed\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_a_bold_status_label_at_the_top_is_the_records_status(tmp_path):
    """The older records state status as a bold label, not a section.

    ADR-006 line 3 and ADR-035 line 5 both predate `## Status` sections. The
    inline form stays supported so their drift remains visible.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n**Status**: Proposed\n\n## Context\n\nWords.\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1


def test_a_bold_status_label_deep_in_the_body_is_not_the_records_status(tmp_path):
    """Unlike the section heading, the inline form stays header-bounded.

    A bold label is not a section. ADR-055 carries `**Status**: COMPLETE` at
    line 119 as a phase result and `**Status**: APPROVED` at line 168 as an
    exception ruling; both were read as that record's lifecycle status before
    this bound existed.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Context\n\nWords.\n\n**Status**: COMPLETE\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


# ── Invalid UTF-8 must be a finding, not a traceback ─────────────────────────
#
# UnicodeDecodeError subclasses ValueError, not OSError, so an `except OSError`
# arm around read_text(encoding="utf-8") never sees it. Before the fix one
# record with a stray byte aborted the whole gate: 97 clean records went
# unreported and the run read as tooling breakage rather than as a finding.
# Reported by Cursor Bugbot on PR #5209 and reproduced before fixing.


def test_a_record_that_is_not_valid_utf8_is_a_violation_not_a_crash(tmp_path):
    """One undecodable record is reported; the rest of the scan still runs."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1))
    (adr_dir / "ADR-002-thing.md").write_bytes(b"\xff\xfe not utf-8")

    counts = _counts(tmp_path)

    assert counts["frontmatter-parses"] == 1
    # `_hits` returns details; the record is on the violation's `path` field,
    # so the identification is asserted there rather than in the message text.
    offenders = [v.path for v in scan(adr_dir, tmp_path) if v.check == "frontmatter-parses"]
    assert offenders == [".project-toolkit/architecture/ADR-002-thing.md"], offenders


def test_the_undecodable_message_names_utf8_not_unreadable(tmp_path):
    """The message must distinguish corrupt bytes from a missing file.

    'could not be read' sends the reader to permissions and paths. The fix for
    a stray byte is a different action, so the two paths do not share wording.
    """
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_bytes(b"\xff\xfe not utf-8")

    (violation,) = scan(adr_dir, tmp_path)

    assert "is not valid UTF-8" in violation.detail
    assert "could not be read" not in violation.detail


def test_a_clean_corpus_reports_no_utf8_violation(tmp_path):
    """Negative control: the new arm does not fire on decodable records.

    Without this, a handler that returned the violation unconditionally would
    pass the two tests above and be indistinguishable from a correct one.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1))
    _write(adr_dir, 2, _valid(2))

    assert _counts(tmp_path)["frontmatter-parses"] == 0


def test_a_baseline_that_is_not_valid_utf8_is_a_config_error(tmp_path):
    """A corrupt baseline degrades to the same one-line reason as any other."""
    from check_adr_lifecycle import read_baseline

    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(b"\xff\xfe not utf-8")

    reason = read_baseline(baseline)

    assert isinstance(reason, str)
    assert "is not valid UTF-8" in reason


def test_a_corrupt_baseline_exits_config_rather_than_traceback(tmp_path):
    """End to end: the process exits ADR-035 config, with no traceback."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(b"\xff\xfe not utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_CONFIG
    assert "Traceback" not in result.stderr
    assert "is not valid UTF-8" in result.stderr


# ── Duplicate frontmatter keys are a forgery vector, not a formatting nit ─────
#
# PyYAML resolves duplicates last-wins and reports nothing, so a record carrying
# `status: proposed` near the top and `status: accepted` lower in the same block
# parses as accepted while reading as proposed to anyone scanning the first
# lines. Reported by Copilot on PR #5209, which noted this repo already treats
# it as a governance risk in detect_adr_changes._has_duplicate_keys.


def test_a_duplicate_status_key_is_a_violation(tmp_path):
    """The declaration a human sees and the one tooling enforces must agree."""
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        "---\nid: ADR-001\nstatus: proposed\ndate: 2026-08-21\n"
        "status: accepted\n---\n\n# ADR-001: Thing\n",
        encoding="utf-8",
    )

    (violation,) = scan(adr_dir, tmp_path)

    assert violation.check == "frontmatter-parses"
    assert "declares `status` twice" in violation.detail


def test_the_duplicate_message_names_the_offending_key(tmp_path):
    """Naming the key is the difference between a fix and a hunt."""
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        "---\nid: ADR-001\nid: ADR-002\nstatus: accepted\n---\n\n# ADR-001: Thing\n",
        encoding="utf-8",
    )

    (violation,) = scan(adr_dir, tmp_path)

    assert "declares `id` twice" in violation.detail


def test_a_record_with_no_duplicates_is_not_flagged(tmp_path):
    """Negative control.

    A checker that returned the violation unconditionally would satisfy both
    tests above and be indistinguishable from a correct one.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1))

    assert _counts(tmp_path)["frontmatter-parses"] == 0


def test_a_repeated_key_nested_under_a_mapping_is_now_caught_too(tmp_path):
    """A duplicate inside a nested mapping is a duplicate.

    This asserted the opposite while the check was a line scan, which could see
    only top-level keys and called that a feature. Moving detection into the
    parser (PR #5230, after Copilot showed quoting evades a line scan) makes the
    nested case visible, and there was never a reason to want it hidden: PyYAML
    resolves `note: a` / `note: b` last-wins here exactly as it does at the top
    level.

    Kept as its own case rather than folded into the spelling matrix below,
    because it is the one a line scan structurally cannot reach.
    """
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        "---\nid: ADR-001\nstatus: accepted\ndate: 2026-08-21\n"
        "decision-makers: []\nsupersedes: []\nsuperseded-by: null\n"
        "explainer: null\nimplemented: true\n"
        "meta:\n  note: a\n  note: b\n---\n\n# ADR-001: Thing\n",
        encoding="utf-8",
    )

    hits = [v for v in scan(adr_dir, tmp_path) if v.check == "frontmatter-parses"]

    assert len(hits) == 1
    assert "declares `note` twice" in hits[0].detail


def test_a_valid_nested_mapping_is_still_clean(tmp_path):
    """Negative control for the case above.

    The original test existed to stop nested mappings being reported wholesale.
    That concern is real, so it keeps a test: distinct nested keys must pass.
    Without this, a checker that flagged every nested mapping would satisfy the
    positive case above and be indistinguishable from a correct one.
    """
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        "---\nid: ADR-001\nstatus: accepted\ndate: 2026-08-21\n"
        "decision-makers: []\nsupersedes: []\nsuperseded-by: null\n"
        "explainer: null\nimplemented: true\n"
        "meta:\n  note: a\n  other: b\n---\n\n# ADR-001: Thing\n",
        encoding="utf-8",
    )

    hits = [v for v in scan(adr_dir, tmp_path) if v.check == "frontmatter-parses"]

    assert hits == []


@pytest.mark.parametrize(
    "first_line",
    [
        "status: proposed",
        '"status": proposed',
        "'status': proposed",
        "status : proposed",
    ],
)
def test_every_yaml_spelling_of_a_duplicate_status_is_caught(tmp_path, first_line):
    """Quoting must not launder a duplicate past the guard.

    All four spellings are one key to PyYAML, which resolves every one of them
    to `accepted`. The line scan this replaced compared raw prefixes, so it
    asked a different question than the parser did and missed two of the four
    (`"status"` and `'status'`). A guard against forgery that the forger evades
    by adding quotation marks is worse than none, because it reports clean.
    Copilot found it on PR #5230.
    """
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        f"---\nid: ADR-001\n{first_line}\nstatus: accepted\ndate: 2026-08-21\n"
        "decision-makers: []\nsupersedes: []\nsuperseded-by: null\n"
        "explainer: null\nimplemented: true\n---\n\n# ADR-001: Thing\n",
        encoding="utf-8",
    )

    hits = [v for v in scan(adr_dir, tmp_path) if v.check == "frontmatter-parses"]

    assert len(hits) == 1
    assert "declares `status` twice" in hits[0].detail


def test_a_commented_out_repeat_is_not_a_duplicate(tmp_path):
    """A commented line declares nothing and must not be counted."""
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text(
        "---\nid: ADR-001\n# status: proposed\nstatus: accepted\ndate: 2026-08-21\n"
        "decision-makers: []\nsupersedes: []\nsuperseded-by: null\n"
        "explainer: null\nimplemented: true\n---\n\n# ADR-001: Thing\n",
        encoding="utf-8",
    )

    hits = [v for v in scan(adr_dir, tmp_path) if v.check == "frontmatter-parses"]

    assert hits == []


# --- status prose: empty sections and fenced samples -------------------------


def test_an_empty_status_section_does_not_borrow_the_next_heading(tmp_path):
    """`## Status` with nothing under it means "", not the next section's title.

    Widening the search to the whole body (PR #5230) broke this contract, which
    `_status_prose`'s docstring still promised: the scan ran to EOF and returned
    the first non-blank line, which for an empty section is the next `##`
    heading. The gate then compared the frontmatter enum against the literal
    text `## Context` and reported drift on a record whose only fault was an
    empty section. Bugbot found it; the fix arrived without a test, which is
    what this is.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n## Status\n\n## Context\n\nWords.\n")

    hits = _hits(tmp_path, "prose-frontmatter-agree")

    assert len(hits) == 1
    assert "Context" not in hits[0], "the next heading is not this record's status"


def test_a_status_section_with_prose_still_reads_its_prose(tmp_path):
    """Negative control: the empty-section guard must not blank real prose."""
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Status\n\nAccepted after review.\n\n## Context\n\nWords.\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_a_status_heading_inside_a_code_fence_is_not_the_records_status(tmp_path):
    """A `## Status` in a markdown sample belongs to the sample.

    ADR-022 carries exactly this at line 521, inside an ADR template it
    documents. It is masked today only because ADR-022's real `## Status` sits
    at line 3 and the search takes the first match; removing that section, the
    direction this campaign is already moving in, would expose it. Searching the
    whole body without blanking code blocks is the same whole-file-scan defect
    the search was widened to fix, one layer down.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Context\n\nWords.\n\n```markdown\n## Status\n\nProposed\n```\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0, (
        "a fenced sample must not be read as the record's own status"
    )


def test_a_real_status_after_a_fenced_sample_is_still_found(tmp_path):
    """Negative control: blanking code must not blank the real section.

    Without this, a checker that discarded the whole body would satisfy the
    fenced case above and be indistinguishable from a correct one.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n```markdown\n## Status\n\nAccepted\n```\n\n## Status\n\nProposed\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1


def test_a_status_heading_inside_an_html_comment_is_not_the_records_status(tmp_path):
    """A `## Status` inside an HTML comment belongs to the comment.

    `blank_code_block_lines` (used before this fix) blanks fenced/indented
    code but deliberately leaves HTML block content, including comments,
    visible: a different caller (`check_skill_md_portability.py`) needs that
    content scannable. ADR-TEMPLATE.md carries exactly this shape, an HTML
    comment documenting a former `## Status` section. `_status_prose` now
    uses `blank_non_prose_block_lines`, which blanks HTML blocks too, so the
    comment's text is masked the same way a fenced sample already was.
    Copilot found this independently on both PR #5230 and the PR #5209
    round-4 review.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n## Context\n\nWords.\n\n<!--\n## Status\n\nProposed\n-->\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0, (
        "an HTML comment must not be read as the record's own status"
    )


def test_a_real_status_after_an_html_comment_is_still_found(tmp_path):
    """Negative control: blanking HTML must not blank the real section.

    Frontmatter says `accepted`; the comment forges an `Accepted` match
    while the real section, further down, says `Proposed`. An unfixed
    scanner reports 0 violations here (the forged match hides the real
    drift); the fix must report 1.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1),
        "\n<!--\n## Status\n\nAccepted\n-->\n\n## Status\n\nProposed\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1, (
        "an HTML-comment-hidden status must not mask real drift"
    )


# --- review-by (issue #5193) ------------------------------------------------

_TODAY = date(2026, 10, 13)
_REVIEW_BY_CHECKS = ("review-by-format", "review-by-past-due", "review-by-prose-date")


def _review_counts(tmp_path: Path, today: date = _TODAY) -> dict[str, int]:
    found = identities(scan(tmp_path / ".project-toolkit" / "architecture", tmp_path, today))
    return {name: sum(found[name].values()) for name in _REVIEW_BY_CHECKS}


def _review_record(
    tmp_path: Path,
    review_by: object,
    prose: str = "Re-review by 2026-10-13.",
    status: str = "accepted",
) -> None:
    """One ADR whose frontmatter carries ``review-by`` and whose body carries ``prose``."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, status=status, **{"review-by": review_by}), f"\n{prose}\n")


def test_a_record_without_review_by_has_no_review_by_finding(tmp_path):
    _write(_adr_dir(tmp_path), 1, _valid(1))

    assert _review_counts(tmp_path) == dict.fromkeys(_REVIEW_BY_CHECKS, 0)


def test_a_null_review_by_has_no_finding(tmp_path):
    _review_record(tmp_path, "null", prose="No deadline.")

    assert _review_counts(tmp_path) == dict.fromkeys(_REVIEW_BY_CHECKS, 0)


def test_a_future_date_stated_in_prose_passes(tmp_path):
    _review_record(tmp_path, "2026-10-18", prose="Re-review by 2026-10-18 (90 days).")

    assert _review_counts(tmp_path) == dict.fromkeys(_REVIEW_BY_CHECKS, 0)


def test_a_past_date_is_a_named_past_due_violation(tmp_path):
    _review_record(tmp_path, "2026-09-27", prose="Review checkpoint is 2026-09-27.")

    assert _review_counts(tmp_path) == {
        "review-by-format": 0,
        "review-by-past-due": 1,
        "review-by-prose-date": 0,
    }


def test_the_past_due_detail_names_the_date_and_the_days_late(tmp_path):
    _review_record(tmp_path, "2026-10-10", prose="Re-review by 2026-10-10.")

    found = scan(tmp_path / ".project-toolkit" / "architecture", tmp_path, _TODAY)
    messages = [v.detail for v in found if v.check == "review-by-past-due"]
    assert len(messages) == 1
    assert "2026-10-10" in messages[0]
    assert "passed 3 day(s) before 2026-10-13" in messages[0]


def test_a_date_due_today_is_still_on_time(tmp_path):
    _review_record(tmp_path, "2026-10-13", prose="Re-review by 2026-10-13.")

    assert _review_counts(tmp_path)["review-by-past-due"] == 0


def test_the_day_after_the_due_date_is_late(tmp_path):
    _review_record(tmp_path, "2026-10-13", prose="Re-review by 2026-10-13.")

    assert _review_counts(tmp_path, date(2026, 10, 14))["review-by-past-due"] == 1


def test_a_proposed_record_is_as_live_as_an_accepted_one(tmp_path):
    _review_record(tmp_path, "2026-09-27", prose="Checkpoint 2026-09-27.", status="proposed")

    assert _review_counts(tmp_path)["review-by-past-due"] == 1


def test_a_quoted_date_parses_like_an_unquoted_one(tmp_path):
    _review_record(tmp_path, "'2026-09-27'", prose="Checkpoint 2026-09-27.")

    assert _review_counts(tmp_path) == {
        "review-by-format": 0,
        "review-by-past-due": 1,
        "review-by-prose-date": 0,
    }


@pytest.mark.parametrize(
    "value",
    [
        "2026-9-27",
        "soon",
        "20260927",
        "'2026-02-30'",
        "2026-09-27 10:00:00",
        "true",
        "[2026-09-27]",
        "''",
    ],
)
def test_a_malformed_review_by_is_one_format_finding_and_nothing_else(tmp_path, value):
    _review_record(tmp_path, value, prose="Re-review by 2026-09-27.")

    assert _review_counts(tmp_path) == {
        "review-by-format": 1,
        "review-by-past-due": 0,
        "review-by-prose-date": 0,
    }


def test_a_date_missing_from_the_prose_is_a_prose_date_finding(tmp_path):
    _review_record(tmp_path, "2026-12-01", prose="No date is stated here.")

    assert _review_counts(tmp_path) == {
        "review-by-format": 0,
        "review-by-past-due": 0,
        "review-by-prose-date": 1,
    }


def test_a_different_date_in_the_prose_does_not_satisfy_the_check(tmp_path):
    _review_record(tmp_path, "2026-12-01", prose="Re-review by 2026-12-02.")

    assert _review_counts(tmp_path)["review-by-prose-date"] == 1


def test_a_date_that_is_a_prefix_of_a_longer_number_does_not_count(tmp_path):
    _review_record(tmp_path, "2026-12-01", prose="Ticket 2026-12-011 and 12026-12-01.")

    assert _review_counts(tmp_path)["review-by-prose-date"] == 1


def test_a_date_inside_a_code_fence_is_not_prose(tmp_path):
    fenced = "```text\nreview-by: 2026-12-01\n```"
    _review_record(tmp_path, "2026-12-01", prose=fenced)

    assert _review_counts(tmp_path)["review-by-prose-date"] == 1


def test_an_unparseable_body_is_a_prose_date_finding_not_a_skip(tmp_path):
    quote = ">" * 20 + " "
    body = "\n" + quote + "```\n" + quote + "## Decision\n" + quote + "```\n"
    _write(_adr_dir(tmp_path), 1, _valid(1, **{"review-by": "2026-12-01"}), body)

    found = scan(tmp_path / ".project-toolkit" / "architecture", tmp_path, _TODAY)
    messages = [v.detail for v in found if v.check == "review-by-prose-date"]

    assert len(messages) == 1
    assert "could not be parsed" in messages[0]


def test_a_date_in_the_status_section_counts_as_prose(tmp_path):
    prose = "## Status\n\nAccepted. The review checkpoint is 2026-12-01."
    _review_record(tmp_path, "2026-12-01", prose=prose)

    assert _review_counts(tmp_path)["review-by-prose-date"] == 0


@pytest.mark.parametrize("status", ["deprecated", "rejected"])
def test_a_closed_record_skips_the_past_due_and_prose_date_checks(tmp_path, status):
    _review_record(tmp_path, "2026-01-17", prose="Nothing about a date.", status=status)

    assert _review_counts(tmp_path) == dict.fromkeys(_REVIEW_BY_CHECKS, 0)


def test_a_superseded_record_skips_the_past_due_and_prose_date_checks(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir,
        1,
        _valid(1, status="superseded", **{"superseded-by": "ADR-002", "review-by": "2026-01-17"}),
    )
    _write(adr_dir, 2, _valid(2, supersedes="[ADR-001]"))

    assert _review_counts(tmp_path) == dict.fromkeys(_REVIEW_BY_CHECKS, 0)


def test_a_closed_record_with_a_malformed_value_still_reports_the_format(tmp_path):
    _review_record(tmp_path, "soon", status="deprecated")

    assert _review_counts(tmp_path)["review-by-format"] == 1


def test_scan_without_a_clock_argument_reads_the_current_date(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, **{"review-by": "2000-01-01"}), "\nBy 2000-01-01.\n")
    _write(adr_dir, 2, _valid(2, **{"review-by": "2999-01-01"}), "\nBy 2999-01-01.\n")

    late = [v.path for v in scan(adr_dir, tmp_path) if v.check == "review-by-past-due"]

    assert late == [_rel(1)]


def test_a_past_due_record_fails_the_ratchet_until_it_is_baselined(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, **{"review-by": "2000-01-01"}), "\nBy 2000-01-01.\n")

    bare = _run(tmp_path, "--baseline", str(_baseline(tmp_path)))
    held = _run(
        tmp_path, "--baseline", str(_baseline(tmp_path, **{"review-by-past-due": {_rel(1): 1}}))
    )

    assert bare.returncode == EXIT_REGRESSION
    assert "review-by-past-due" in bare.stdout
    assert held.returncode == EXIT_OK


def test_the_review_by_checks_are_registered_in_check_order():
    assert CHECKS[-3:] == _REVIEW_BY_CHECKS
