#!/usr/bin/env python3
"""Combine statement-only main coverage data with branch-mode pin data.

`.github/workflows/pytest.yml`, job `test`, runs pytest three times: once over
almost the whole suite ("Run pytest") and once each for the two disjoint
groups of files pinned at a 100% *branch* gate on one narrow module apiece
("Pin ai_review_common.verdict coverage collection (REQ-008-07)" and "Pin
REQ-009 module coverage collection (PR #1989 user requirement)"). The main
run stays statement-only on purpose: turning on --cov-branch there cost
+27.02s wall (438.91s -> 465.93s, +6.2%, measured) for a branch percentage
nothing in that step gates. The two pin steps need real branch (arc) data,
because the 100% gate against their pinned module is a branch gate, so they
keep --cov-branch.

Evidence:
.agents/sessions/2026-08-06-session-10003-profile-optimize-pre-submit-pre-commit-pre-push.json

This module docstring is the one place the +27.02s/+6.2% measurement is
recorded; `.github/workflows/pytest.yml` points here rather than repeating
the numbers.

Both pin steps collect BROAD coverage (bare --cov, the same source list as
the main run), not narrowed to their one pinned module. The five files those
two steps run also exercise other modules incidentally; a narrow --cov target
would mean pytest-cov never measures those other modules there at all, and no
downstream tool -- this script included -- can recover data collection never
produced. The 100% branch gate for each pin's own pinned module still applies
exactly, isolated from that broader collection: `.github/workflows/pytest.yml`
runs `coverage report --data-file=<pin-data> --include=<pinned module path(s)>
--fail-under=100` immediately after each pin's collection step, and `--include`
filters the *report* only, so incidental modules in the same data file cannot
move that module's own percentage in either direction. This script has no
awareness of, and does not re-enforce, that gate; it only projects and unions
all measured lines, pinned module and incidental alike.

`coverage combine` (coverage.sqldata.CoverageData.update) refuses to mix arc
rows with line rows in one data file: "Can't combine statement coverage data
with branch data". Combining the three files above cannot go through a plain
`coverage combine` call for exactly that reason. This script instead projects
each pin's arc data down to the lines it executed -- the same reduction
`coverage.py` performs internally to report line coverage from branch data --
and unions those projected lines into the main run's statement data, so the
result is a single line-coverage data file `coverage xml` can read directly.
Projecting the whole pin data file, not just the pinned module's slice of it,
is what carries the incidental modules' lines into the final report.

Every input is validated before anything is written: each file must exist, be
a readable coverage data file, contain at least one measured row, and be in
the mode this tool expects for that input (statement-only for --main-data,
branch/arc for --pin-data). Any failure raises and this script exits nonzero;
there is no partial or empty fallback output.

Exit codes (AGENTS.md contract):
    0 - ok, combined data file written
    1 - an input data file failed validation (missing, unreadable, empty, or
        wrong measurement mode)
    2 - usage error (bad CLI arguments; argparse itself exits with this code)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import coverage
from coverage.exceptions import CoverageException

EXIT_OK = 0
EXIT_INVALID_DATA = 1
EXIT_USAGE = 2


class CoverageInputError(Exception):
    """An input coverage data file failed validation.

    The message always names the offending file and the reason, so a CI log
    identifies the bad input without needing to reproduce locally.
    """


def _load_data(path: Path, *, label: str) -> coverage.CoverageData:
    """Read `path` into a CoverageData object, or raise CoverageInputError.

    Covers every failure mode this tool must not swallow: a missing file, a
    file that exists but is not a coverage data file (corrupt or foreign
    content), and a file that reads cleanly but holds zero measured rows.
    """
    if not path.is_file():
        raise CoverageInputError(f"{label} coverage data file not found: {path}")

    data = coverage.CoverageData(basename=str(path))
    try:
        data.read()
    except (CoverageException, OSError) as exc:
        raise CoverageInputError(f"{label} coverage data file unreadable at {path}: {exc}") from exc

    if not data:
        raise CoverageInputError(f"{label} coverage data file is empty: {path}")

    return data


def _require_branch_data(data: coverage.CoverageData, *, label: str, path: Path) -> None:
    """Raise unless `data` holds arc (branch) rows, i.e. was collected with --cov-branch."""
    if not data.has_arcs():
        raise CoverageInputError(
            f"{label} coverage data file at {path} is statement-only data; "
            "pin data must be collected with --cov-branch"
        )


def _require_statement_data(data: coverage.CoverageData, *, label: str, path: Path) -> None:
    """Raise unless `data` holds line (statement) rows, not arc (branch) rows."""
    if data.has_arcs():
        raise CoverageInputError(
            f"{label} coverage data file at {path} is branch (arc) data; "
            "main data must be collected without --cov-branch"
        )


def _project_to_lines(data: coverage.CoverageData, scratch_path: Path) -> coverage.CoverageData:
    """Write the lines `data` executed to `scratch_path` and read them back.

    `CoverageData.lines()` returns the executed line numbers for a file
    regardless of whether the source data holds arcs or lines; this is the
    same reduction `coverage report`'s line-coverage percentage is computed
    from even when the underlying data has branches. Discarding the arc
    (branch-transition) detail this way is what makes the result combinable
    with the main run's statement-only data.

    This writes to a real file and reads it back rather than returning an
    in-memory (`no_disk=True`) CoverageData. Confirmed on coverage 7.13.1
    (pinned in uv.lock): `CoverageData.update()` attaches the source's SQLite
    file via a bound-parameter `ATTACH DATABASE`, and the destination's own
    connection is not opened with `uri=True` (it is a plain disk path), so a
    `no_disk` source's shared-cache memory URI is attached as a literal
    on-disk filename instead of being recognized as a URI, and the update
    fails with "no such table: other_db.file". A real file sidesteps that
    entirely; confirmed absent on coverage 7.14.1, so re-check this note
    before assuming it still applies across a coverage.py upgrade.
    """
    scratch_path.unlink(missing_ok=True)
    projected = coverage.CoverageData(basename=str(scratch_path))
    line_map = {filename: (data.lines(filename) or []) for filename in data.measured_files()}
    if line_map:
        projected.add_lines(line_map)
    projected.write()

    read_back = coverage.CoverageData(basename=str(scratch_path))
    read_back.read()
    return read_back


def combine(main_path: Path, pin_paths: list[Path], output_path: Path) -> None:
    """Validate every input, then write their line-coverage union to `output_path`.

    Raises CoverageInputError, naming the offending file, on any invalid
    input (missing, unreadable, empty, or wrong mode). Reading happens for
    every input before anything is written, so a bad pin file never produces
    a combined file holding only the main run's data.
    """
    main_data = _load_data(main_path, label="main")
    _require_statement_data(main_data, label="main", path=main_path)

    pin_data_list: list[coverage.CoverageData] = []
    for index, pin_path in enumerate(pin_paths):
        label = f"pin[{index}] ({pin_path.name})"
        pin_data = _load_data(pin_path, label=label)
        _require_branch_data(pin_data, label=label, path=pin_path)
        pin_data_list.append(pin_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # An output file left over from a previous run would otherwise be reused
    # (CoverageData opens rather than truncates an existing file), silently
    # merging stale rows into this run's result.
    output_path.unlink(missing_ok=True)

    combined = coverage.CoverageData(basename=str(output_path))
    combined.update(main_data)
    for index, pin_data in enumerate(pin_data_list):
        scratch_path = output_path.parent / f".{output_path.name}.pin{index}.projected"
        try:
            combined.update(_project_to_lines(pin_data, scratch_path))
        finally:
            scratch_path.unlink(missing_ok=True)
    combined.write()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--main-data",
        required=True,
        type=Path,
        help="Statement-only (no --cov-branch) main-run coverage data file",
    )
    parser.add_argument(
        "--pin-data",
        required=True,
        action="append",
        type=Path,
        help="Branch (--cov-branch) pin-run coverage data file; repeat once per pin",
    )
    parser.add_argument(
        "--output-data",
        required=True,
        type=Path,
        help="Path to write the combined line-coverage data file",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        combine(args.main_data, args.pin_data, args.output_data)
    except CoverageInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_DATA

    print(f"Combined {1 + len(args.pin_data)} coverage data file(s) into {args.output_data}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
