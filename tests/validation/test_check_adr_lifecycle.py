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
- implemented-implies-decided: pos (accepted + implemented), neg
  (proposed + implemented), edge (``implemented: "true"`` is not the boolean)
- prose-frontmatter-agree: pos (decorated prose still matches), neg (drift),
  edge (inline ``**Status**:`` counts as the section; an amendment-first line
  is flagged), and the ADR-073 invariant that the gate never rewrites prose

Ratchet and CLI behavior: improvement passes, regression exits 1, baseline
missing / malformed / stale exits 2, missing ADR directory exits 2,
``--write-baseline`` round-trips, and ``main(argv)`` itself returns non-zero on
a regression (``.claude/rules/ci-scripts.md`` MUST 10 and 21).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
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
    _find_cycles,
    main,
    scan,
    tally,
    validate_adr_lifecycle,
)

# --- fixtures ---------------------------------------------------------------


def _adr_dir(tmp_path: Path) -> Path:
    path = tmp_path / ".agents" / "architecture"
    path.mkdir(parents=True)
    return path


def _write(adr_dir: Path, number: int, frontmatter: str | None, body: str = "") -> Path:
    """Write ADR-NNN-thing.md with an optional raw frontmatter block."""
    head = f"---\n{textwrap.dedent(frontmatter).strip()}\n---\n" if frontmatter else ""
    path = adr_dir / f"ADR-{number:03d}-thing.md"
    path.write_text(f"{head}\n# ADR-{number:03d}: Thing\n{body}", encoding="utf-8")
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


_STATUS_SECTION = "\n## Status\n\nAccepted (2026-08-21).\n"


def _counts(tmp_path: Path) -> dict[str, int]:
    return tally(scan(tmp_path / ".agents" / "architecture", tmp_path))


def _hits(tmp_path: Path, check: str) -> list[str]:
    adr_dir = tmp_path / ".agents" / "architecture"
    return [v.detail for v in scan(adr_dir, tmp_path) if v.check == check]


def _baseline(tmp_path: Path, **counts: int) -> Path:
    path = tmp_path / "baseline.json"
    payload = {"counts": {name: counts.get(name, 0) for name in CHECKS}}
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


def test_unterminated_fence_is_reported_as_absent(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    (adr_dir / "ADR-001-thing.md").write_text("---\nid: ADR-001\n\n# ADR-001\n", encoding="utf-8")

    assert _hits(tmp_path, "frontmatter-parses") == [
        "no leading `---` frontmatter block (ADR-073 schema absent)"
    ]


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

    assert "names ADR-008 but the filename says ADR-007" in _hits(
        tmp_path, "id-matches-filename"
    )[0]


@pytest.mark.parametrize("raw_id", ["ADR-7", "adr-007", "ADR_7", 7])
def test_id_reference_forms_all_resolve(tmp_path, raw_id):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 7, _valid(7, id=raw_id), _STATUS_SECTION)

    assert _counts(tmp_path)["id-matches-filename"] == 0


# --- status-enum ------------------------------------------------------------


@pytest.mark.parametrize(
    "status", ["proposed", "accepted", "rejected", "deprecated", "superseded"]
)
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


def test_accepted_and_implemented_is_clean(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1, implemented="true"), _STATUS_SECTION)

    assert _counts(tmp_path)["implemented-implies-decided"] == 0


def test_proposed_and_implemented_is_a_violation(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir, 1, _valid(1, status="proposed", implemented="true"), "\n## Status\n\nProposed\n"
    )

    assert _counts(tmp_path)["implemented-implies-decided"] == 1


def test_implemented_string_true_is_not_the_boolean(tmp_path):
    """Edge: only a YAML boolean flips the gate, so `"true"` must not trip it."""
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir, 1, _valid(1, status="proposed", implemented='"true"'), "\n## Status\n\nProposed\n"
    )

    assert _counts(tmp_path)["implemented-implies-decided"] == 0


# --- prose-frontmatter-agree ------------------------------------------------


@pytest.mark.parametrize(
    "prose",
    [
        "Accepted",
        "**Accepted**",
        "Accepted (amended 2026-07-19: narrowed to hooks).",
        "`Accepted`. Supersedes nothing.",
        "> Accepted by repo-owner authorization.",
        "accepted",
    ],
)
def test_decorated_prose_matching_the_enum_passes(tmp_path, prose):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), f"\n## Status\n\n{prose}\n")

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


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
    line 57 agrees, saying the prose section "may carry" nuance rather than must.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), "\n## Context\n\nWords.\n")

    counts = _counts(tmp_path)

    assert counts["prose-frontmatter-agree"] == 0
    assert "status-section-present" not in counts


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
    baseline = _baseline(tmp_path, **{"frontmatter-parses": 1})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    assert "[PASS]" in result.stdout


def test_a_risen_count_fails_and_names_the_check(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    _write(adr_dir, 2, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": 1})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_REGRESSION
    assert "frontmatter-parses: 1 -> 2" in result.stdout
    assert "Do NOT raise the baseline" in result.stdout


def test_an_improvement_passes_without_rewriting_the_baseline(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, _valid(1), _STATUS_SECTION)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": 5})
    before = baseline.read_text(encoding="utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_OK
    assert "improved, record with --write-baseline" in result.stdout
    assert baseline.read_text(encoding="utf-8") == before


def test_run_reports_which_checks_are_ready_for_zero_tolerance(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = _baseline(tmp_path, **{"frontmatter-parses": 1})

    result = _run(tmp_path, "--baseline", str(baseline))

    assert "Checks at zero and flippable to zero-tolerance:" in result.stdout
    assert "status-enum" in result.stdout


def test_write_baseline_round_trips_and_then_passes(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    _write(
        adr_dir, 2, _valid(2, status="proposed", implemented="true"), "\n## Status\n\nProposed\n"
    )
    baseline = tmp_path / "baseline.json"

    written = _run(tmp_path, "--baseline", str(baseline), "--write-baseline")

    assert written.returncode == EXIT_OK
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    assert payload["counts"]["frontmatter-parses"] == 1
    assert payload["counts"]["implemented-implies-decided"] == 1
    assert list(payload["counts"]) == list(CHECKS)
    assert _run(tmp_path, "--baseline", str(baseline)).returncode == EXIT_OK


def test_missing_baseline_is_a_config_error(tmp_path):
    _adr_dir(tmp_path)

    result = _run(tmp_path, "--baseline", str(tmp_path / "absent.json"))

    assert result.returncode == EXIT_CONFIG
    assert "could not be read" in result.stderr


def test_malformed_baseline_is_a_config_error(tmp_path):
    _adr_dir(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{not json", encoding="utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_CONFIG
    assert "not valid JSON" in result.stderr


def test_baseline_missing_a_check_is_a_config_error(tmp_path):
    _adr_dir(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"counts": {"status-enum": 0}}), encoding="utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_CONFIG
    assert "does not match the check list" in result.stderr


def test_baseline_with_a_non_count_value_is_a_config_error(tmp_path):
    _adr_dir(tmp_path)
    baseline = tmp_path / "baseline.json"
    counts = dict.fromkeys(CHECKS, 0)
    counts["status-enum"] = -1
    baseline.write_text(json.dumps({"counts": counts}), encoding="utf-8")

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


def test_main_returns_nonzero_on_a_regression(tmp_path):
    """CLI exit contract: the process, not just a helper, must report failure."""
    adr_dir = _adr_dir(tmp_path)
    _write(adr_dir, 1, None)
    baseline = _baseline(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == EXIT_REGRESSION


def test_main_returns_config_code_on_a_bad_limit(tmp_path):
    _adr_dir(tmp_path)

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
    _adr_dir(tmp_path)
    monkeypatch.setattr("check_adr_lifecycle._BASELINE_PATH", tmp_path / "absent.json")

    assert validate_adr_lifecycle(tmp_path) is False


# --- the shipped baseline ---------------------------------------------------


def test_the_shipped_baseline_covers_every_check():
    payload = json.loads(
        (_VALIDATION_DIR / "adr_lifecycle_baseline.json").read_text(encoding="utf-8")
    )

    assert list(payload["counts"]) == list(CHECKS)
    assert all(isinstance(value, int) and value >= 0 for value in payload["counts"].values())


def test_the_repository_corpus_does_not_exceed_the_shipped_baseline():
    """ci-scripts.md MUST 13: the gate must pass against the full corpus."""
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
    baseline = _baseline(tmp_path, **{"frontmatter-parses": 1})

    result = _run(tmp_path, "--baseline", str(baseline), "--show-all")

    assert result.returncode == EXIT_OK
    assert "All 1 violation(s):" in result.stdout


def test_read_baseline_rejects_a_payload_without_counts(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"schema_version": "1"}), encoding="utf-8")

    assert "has no `counts` mapping" in read_baseline(path)


def test_read_baseline_rejects_an_unknown_check_name(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    counts = dict.fromkeys(CHECKS, 0)
    counts["retired-check"] = 0
    path.write_text(json.dumps({"counts": counts}), encoding="utf-8")

    assert "unknown: ['retired-check']" in read_baseline(path)


def test_read_baseline_rejects_a_boolean_count(tmp_path):
    from check_adr_lifecycle import read_baseline

    path = tmp_path / "baseline.json"
    counts: dict[str, object] = dict.fromkeys(CHECKS, 0)
    counts["status-enum"] = True
    path.write_text(json.dumps({"counts": counts}), encoding="utf-8")

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
    baseline = _baseline(tmp_path, **dict.fromkeys(CHECKS, 1))

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
        adr_dir, 1, _valid(1),
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
        adr_dir, 1, _valid(1),
        "\n## Provenance\n\nRenumbered by PR #1604.\n"
        "\n## Migration\n\n**Status**: COMPLETE (2025-12-29)\n"
        "\n## Exceptions\n\n**Status**: APPROVED\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 0


def test_record_status_is_still_found_when_it_is_the_first_section(tmp_path):
    """Positive control: scoping must not stop the gate seeing a real drift."""
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir, 1, _valid(1),
        "\n## Status\n\nProposed\n\n## Context\n\nWords.\n",
    )

    assert _counts(tmp_path)["prose-frontmatter-agree"] == 1


def test_status_heading_after_another_section_is_out_of_scope(tmp_path):
    """The header region ends at the first non-Status level-2 heading.

    A record that opens with Context and only later carries a Status heading is
    not stating its lifecycle in a header, and the gate does not guess.
    """
    adr_dir = _adr_dir(tmp_path)
    _write(
        adr_dir, 1, _valid(1),
        "\n## Context\n\nWords.\n\n## Status\n\nProposed\n",
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
    offenders = [
        v.path for v in scan(adr_dir, tmp_path) if v.check == "frontmatter-parses"
    ]
    assert offenders == [".agents/architecture/ADR-002-thing.md"], offenders


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
    _adr_dir(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(b"\xff\xfe not utf-8")

    result = _run(tmp_path, "--baseline", str(baseline))

    assert result.returncode == EXIT_CONFIG
    assert "Traceback" not in result.stderr
    assert "is not valid UTF-8" in result.stderr
