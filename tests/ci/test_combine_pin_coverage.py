"""Tests for scripts/ci/combine_pin_coverage.py.

`.github/workflows/pytest.yml`, job `test`, runs pytest three times: a
statement-only main run over almost the whole suite, and two branch-mode
(--cov-branch) pin runs that each own a disjoint slice of files pinned at a
100% branch gate on one narrow module apiece. `coverage combine` cannot merge
those three data files directly, because it refuses to mix arc (branch) rows
with line (statement) rows in one file. This module's `combine()` instead
validates every input, projects the two branch files down to the lines they
executed, and unions those projections into the main run's statement data.

Both pin runs collect BROAD branch data (their pytest invocation uses bare
--cov, not a narrow module target), because the five files they own also
exercise other modules incidentally. `combine()` has no notion of a "pinned
module": it projects every measured file in each pin's arc data to lines,
pinned module and incidental module alike, so nothing here filters incidental
coverage out. The 100% branch gate stays exact and isolated to each pin's one
pinned module regardless, because that gate lives entirely outside this
script: `.github/workflows/pytest.yml` runs `coverage report --data-file=...
--include=<pinned module path(s)> --fail-under=100` against each pin's raw
data file, before this script ever runs, and `--include` filters that report
without touching the underlying data. See
`test_target_only_report_gate_ignores_incidental_module_coverage` below for a
subprocess-level proof of that isolation, and
`test_combine_projects_incidental_module_lines_alongside_pinned_module` for
proof that combine() itself does not drop or filter incidental lines.

See the module docstring in `scripts/ci/combine_pin_coverage.py` for the
+27.02s (+6.2%) wall-time measurement behind keeping the main run
statement-only rather than enabling --cov-branch there to sidestep this.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import coverage
import pytest

from scripts.ci import combine_pin_coverage as cpc


def _write_arc_data(basename: Path, source: Path, arcs: list[tuple[int, int]]) -> None:
    """Write a branch-coverage (arc) data file, matching a --cov-branch run."""
    data = coverage.CoverageData(basename=str(basename))
    data.add_arcs({str(source): arcs})
    data.write()


def _write_line_data(basename: Path, source: Path, lines: list[int]) -> None:
    """Write a statement-only data file, matching a run without --cov-branch."""
    data = coverage.CoverageData(basename=str(basename))
    data.add_lines({str(source): lines})
    data.write()


def test_combine_writes_line_only_union_of_main_and_two_pin_files(tmp_path: Path) -> None:
    """Positive path against real CoverageData: a statement-only main file plus
    two branch-mode pin files (each covering a different source file) combine
    into one line-coverage file holding the union of all three."""
    mod = tmp_path / "mod.py"
    other = tmp_path / "other.py"
    main_data = tmp_path / ".coverage.main"
    pin_a = tmp_path / ".coverage.pin-a"
    pin_b = tmp_path / ".coverage.pin-b"
    output = tmp_path / ".coverage.combined"

    _write_line_data(main_data, mod, [1, 2, 3])
    _write_arc_data(pin_a, mod, [(-1, 1), (1, 4), (4, -1)])
    _write_arc_data(pin_b, other, [(-1, 1), (1, 2), (2, -1)])

    cpc.combine([main_data], [pin_a, pin_b], output)

    result = coverage.CoverageData(basename=str(output))
    result.read()
    assert not result.has_arcs(), "combined output must be line-only, not branch, data"
    assert sorted(result.lines(str(mod)) or []) == [1, 2, 3, 4]
    assert sorted(result.lines(str(other)) or []) == [1, 2]


def test_combine_unions_multiple_statement_partitions_before_pin_data(tmp_path: Path) -> None:
    bulk_module = tmp_path / "bulk.py"
    mutation_module = tmp_path / "mutation.py"
    pinned_module = tmp_path / "pinned.py"
    bulk_data = tmp_path / ".coverage.bulk"
    mutation_data = tmp_path / ".coverage.mutation"
    pin_data = tmp_path / ".coverage.pin"
    output = tmp_path / ".coverage.combined"

    _write_line_data(bulk_data, bulk_module, [1, 2])
    _write_line_data(mutation_data, mutation_module, [3, 4])
    _write_arc_data(pin_data, pinned_module, [(-1, 5), (5, -1)])

    exit_code = cpc.main(
        [
            "--main-data",
            str(bulk_data),
            "--main-data",
            str(mutation_data),
            "--pin-data",
            str(pin_data),
            "--output-data",
            str(output),
        ]
    )

    assert exit_code == cpc.EXIT_OK
    result = coverage.CoverageData(basename=str(output))
    result.read()
    assert sorted(result.lines(str(bulk_module)) or []) == [1, 2]
    assert sorted(result.lines(str(mutation_module)) or []) == [3, 4]
    assert sorted(result.lines(str(pinned_module)) or []) == [5]


def test_missing_main_file_fails_loudly_and_cli_exits_nonzero(tmp_path: Path) -> None:
    """Missing file: combine() names the path and raises; main(argv) turns that
    into a nonzero exit rather than a silent pass, and writes no output."""
    missing_main = tmp_path / ".coverage.main"
    pin = tmp_path / ".coverage.pin"
    output = tmp_path / ".coverage.combined"
    _write_arc_data(pin, tmp_path / "mod.py", [(-1, 1), (1, -1)])

    with pytest.raises(cpc.CoverageInputError, match="not found"):
        cpc.combine([missing_main], [pin], output)

    exit_code = cpc.main(
        [
            "--main-data",
            str(missing_main),
            "--pin-data",
            str(pin),
            "--output-data",
            str(output),
        ]
    )

    assert exit_code == cpc.EXIT_INVALID_DATA
    assert not output.exists()


def test_pin_data_without_arcs_is_rejected_branch_input_required(tmp_path: Path) -> None:
    """A pin file collected without --cov-branch (statement-only) must be
    rejected: the pins' 100% gate is a branch percentage, so accepting
    statement-only data here would silently drop branch fidelity."""
    mod = tmp_path / "mod.py"
    main_data = tmp_path / ".coverage.main"
    pin_missing_branch = tmp_path / ".coverage.pin"
    _write_line_data(main_data, mod, [1, 2])
    _write_line_data(pin_missing_branch, mod, [3, 4])

    with pytest.raises(cpc.CoverageInputError, match="--cov-branch"):
        cpc.combine([main_data], [pin_missing_branch], tmp_path / ".coverage.combined")


def test_main_data_with_arcs_is_rejected_statement_main_required(tmp_path: Path) -> None:
    """A main file collected with --cov-branch must be rejected: the main run
    is deliberately statement-only (see module docstring), so branch data
    here signals the workflow regressed to enabling --cov-branch on the main
    partition."""
    mod = tmp_path / "mod.py"
    main_with_arcs = tmp_path / ".coverage.main"
    pin = tmp_path / ".coverage.pin"
    _write_arc_data(main_with_arcs, mod, [(-1, 1), (1, 2), (2, -1)])
    _write_arc_data(pin, mod, [(-1, 1), (1, 3), (3, -1)])

    with pytest.raises(cpc.CoverageInputError, match="without --cov-branch"):
        cpc.combine([main_with_arcs], [pin], tmp_path / ".coverage.combined")


def test_project_to_lines_preserves_measured_lines_from_arc_data(tmp_path: Path) -> None:
    """Line projection: arcs (-1,1),(1,2),(2,3),(3,-1) execute lines {1,2,3}.
    The negative endpoints are call-graph entry/exit sentinels, not line
    numbers, and must not leak into the projection."""
    mod = tmp_path / "mod.py"
    arc_data = coverage.CoverageData(basename=str(tmp_path / ".coverage.arc-source"))
    arc_data.add_arcs({str(mod): [(-1, 1), (1, 2), (2, 3), (3, -1)]})

    projected = cpc._project_to_lines(arc_data, tmp_path / ".coverage.projected")

    assert not projected.has_arcs()
    assert sorted(projected.lines(str(mod)) or []) == [1, 2, 3]


def test_project_to_lines_preserves_incidental_module_alongside_pinned_module(
    tmp_path: Path,
) -> None:
    """A single pin's broad --cov collection produces one arc data file naming
    both its pinned module and modules it touched only incidentally.
    `_project_to_lines` must carry both through: it has no concept of which
    file was "the" target, so nothing here filters the incidental one out."""
    pinned = tmp_path / "pinned_module.py"
    incidental = tmp_path / "incidental_module.py"
    arc_data = coverage.CoverageData(basename=str(tmp_path / ".coverage.pin-broad"))
    # Pinned module: full branch coverage (both arms of the one branch).
    arc_data.add_arcs({str(pinned): [(-1, 1), (1, 2), (2, 3), (2, 4), (3, -1), (4, -1)]})
    # Incidental module: only one arm of its branch executed, i.e. this module
    # is NOT at 100% branch coverage; it must still show up in the projection.
    arc_data.add_arcs({str(incidental): [(-1, 1), (1, 2), (2, 3), (3, -1)]})

    projected = cpc._project_to_lines(arc_data, tmp_path / ".coverage.projected")

    assert not projected.has_arcs()
    assert sorted(projected.lines(str(pinned)) or []) == [1, 2, 3, 4]
    assert sorted(projected.lines(str(incidental)) or []) == [1, 2, 3]


def test_combine_projects_incidental_module_lines_alongside_pinned_module(
    tmp_path: Path,
) -> None:
    """End-to-end through combine(): the main run never touches either module
    the pin below measures (it --ignore's the pin-owned test files), so every
    line reported for them in the final combined data must come from the
    pin's own broad collection. Both the pinned module and the module it
    measured only incidentally must appear in the combined output; dropping
    the incidental one here is exactly the correctness gap this design fixes,
    because a narrow --cov target on the pin would have meant pytest-cov never
    produced incidental_module rows to combine in the first place."""
    pinned = tmp_path / "pinned_module.py"
    incidental = tmp_path / "incidental_module.py"
    unrelated_main_mod = tmp_path / "unrelated_main_mod.py"
    main_data = tmp_path / ".coverage.main"
    pin_data = tmp_path / ".coverage.pin-broad"
    output = tmp_path / ".coverage.combined"

    # Main run: statement-only, and never mentions either module the pin owns
    # (mirrors "Run pytest" --ignore'ing the pin-owned test files).
    _write_line_data(main_data, unrelated_main_mod, [1, 2])
    _write_arc_data(pin_data, pinned, [(-1, 1), (1, 2), (2, 3), (2, 4), (3, -1), (4, -1)])
    arc_data = coverage.CoverageData(basename=str(pin_data))
    arc_data.read()
    arc_data.add_arcs({str(incidental): [(-1, 1), (1, 2), (2, 3), (3, -1)]})
    arc_data.write()

    cpc.combine([main_data], [pin_data], output)

    result = coverage.CoverageData(basename=str(output))
    result.read()
    assert sorted(result.lines(str(pinned)) or []) == [1, 2, 3, 4]
    assert sorted(result.lines(str(incidental)) or []) == [1, 2, 3], (
        "incidental module's lines must survive into the final combined data, "
        "not just the pinned module's"
    )
    assert sorted(result.lines(str(unrelated_main_mod)) or []) == [1, 2]


def test_target_only_report_gate_ignores_incidental_module_coverage(tmp_path: Path) -> None:
    """Proves the CLI assumption `.github/workflows/pytest.yml` leans on: a
    pin's broad collection can hold an incompletely-covered incidental module
    without that module ever touching the pinned module's own 100% branch
    gate, because that gate is `coverage report --data-file=<pin-data>
    --include=<pinned module path> --fail-under=100` run directly against the
    pin's raw (unprojected) data file, before combine_pin_coverage.py runs.

    Two directions, both against one real coverage data file holding both
    modules: the pinned module at 100% branch passes regardless of the
    incidental module's own (here, 67%) branch percentage, and the pinned
    module below 100% branch fails regardless of the incidental module being
    at 100%. Neither module's percentage is diluted or rescued by the other's
    inclusion in the same data file.
    """
    pinned = tmp_path / "pinned_module.py"
    pinned.write_text("def f(x):\n    if x:\n        return 1\n    return 2\n")
    incidental = tmp_path / "incidental_module.py"
    incidental.write_text("def g(y):\n    if y:\n        return 1\n    return 2\n")

    def _report(data_file: Path, include: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                f"--data-file={data_file}",
                f"--include={include}",
                "--fail-under=100",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

    # Pinned module fully covered (both branch arms); incidental module only
    # one arm (67% branch), simulating an incompletely-exercised module the
    # pin's broad collection touched but does not own a gate for.
    pinned_complete = tmp_path / ".coverage.pinned-complete"
    _write_arc_data(pinned_complete, pinned, [(-1, 1), (1, 2), (2, 3), (2, 4), (3, -1), (4, -1)])
    incidental_data = coverage.CoverageData(basename=str(pinned_complete))
    incidental_data.read()
    incidental_data.add_arcs({str(incidental): [(-1, 1), (1, 2), (2, 3), (3, -1)]})
    incidental_data.write()

    passing = _report(pinned_complete, "pinned_module.py")
    assert passing.returncode == 0, (
        f"pinned module at 100% must pass regardless of incidental coverage: "
        f"{passing.stdout}{passing.stderr}"
    )

    # Same file, opposite direction: gate the incidental module's own path
    # (67% branch) and confirm it fails, proving --include actually restricts
    # the percentage to the named path rather than reporting the pinned
    # module's number for any --include argument.
    failing = _report(pinned_complete, "incidental_module.py")
    assert failing.returncode != 0, "incidental module below 100% must fail its own --include gate"
    assert "less than fail-under=100" in failing.stdout

    # Reverse the roles: pinned module below 100% branch, incidental module
    # at 100%. The pinned module's own gate must still fail.
    pinned_incomplete = tmp_path / ".coverage.pinned-incomplete"
    _write_arc_data(pinned_incomplete, pinned, [(-1, 1), (1, 2), (2, 3), (3, -1)])
    incidental_complete = coverage.CoverageData(basename=str(pinned_incomplete))
    incidental_complete.read()
    incidental_complete.add_arcs(
        {str(incidental): [(-1, 1), (1, 2), (2, 3), (2, 4), (3, -1), (4, -1)]}
    )
    incidental_complete.write()

    still_failing = _report(pinned_incomplete, "pinned_module.py")
    assert still_failing.returncode != 0, (
        "pinned module below 100% must fail its own gate even when an "
        "incidental module in the same data file is at 100%"
    )
    assert "less than fail-under=100" in still_failing.stdout


def test_empty_data_file_is_rejected(tmp_path: Path) -> None:
    """A zero-byte data file reads cleanly (valid empty SQLite db) but holds
    no measured rows; it must be rejected, not treated as vacuously fine."""
    main_data = tmp_path / ".coverage.main"
    main_data.touch()
    pin = tmp_path / ".coverage.pin"
    _write_arc_data(pin, tmp_path / "mod.py", [(-1, 1), (1, -1)])

    with pytest.raises(cpc.CoverageInputError, match="empty"):
        cpc.combine([main_data], [pin], tmp_path / ".coverage.combined")


def test_unreadable_data_file_is_rejected(tmp_path: Path) -> None:
    """A file that exists but is not a coverage data file (corrupt or foreign
    content) must be rejected with the underlying reason, not crash unhandled
    or read as empty."""
    corrupt = tmp_path / ".coverage.main"
    corrupt.write_text("not a sqlite database")
    pin = tmp_path / ".coverage.pin"
    _write_arc_data(pin, tmp_path / "mod.py", [(-1, 1), (1, -1)])

    with pytest.raises(cpc.CoverageInputError, match="unreadable"):
        cpc.combine([corrupt], [pin], tmp_path / ".coverage.combined")


def test_main_cli_reports_success_and_writes_combined_file(tmp_path: Path) -> None:
    """CLI success path, exercised through main(argv) rather than combine()
    directly, so the argparse wiring is proven, not only the library call."""
    mod = tmp_path / "mod.py"
    main_data = tmp_path / ".coverage.main"
    pin = tmp_path / ".coverage.pin"
    output = tmp_path / ".coverage.combined"
    _write_line_data(main_data, mod, [1, 2])
    _write_arc_data(pin, mod, [(-1, 1), (1, 3), (3, -1)])

    exit_code = cpc.main(
        [
            "--main-data",
            str(main_data),
            "--pin-data",
            str(pin),
            "--output-data",
            str(output),
        ]
    )

    assert exit_code == cpc.EXIT_OK
    assert output.exists()
    written = coverage.CoverageData(basename=str(output))
    written.read()
    assert sorted(written.lines(str(mod)) or []) == [1, 2, 3]


def test_stale_output_file_is_not_reused(tmp_path: Path) -> None:
    """A leftover output file from a previous run must not be merged into the
    new result: CoverageData opens rather than truncates an existing file, so
    combine() must remove it first or stale rows would silently survive."""
    mod = tmp_path / "mod.py"
    other = tmp_path / "other.py"
    main_data = tmp_path / ".coverage.main"
    pin = tmp_path / ".coverage.pin"
    output = tmp_path / ".coverage.combined"
    _write_line_data(main_data, mod, [1, 2])
    _write_arc_data(pin, mod, [(-1, 1), (1, 2), (2, -1)])

    # Stale output file from an unrelated earlier run, naming a file this
    # run's inputs never mention.
    _write_line_data(output, other, [99])

    cpc.combine([main_data], [pin], output)

    result = coverage.CoverageData(basename=str(output))
    result.read()
    assert other.as_posix() not in {Path(f).as_posix() for f in result.measured_files()}
    assert sorted(result.lines(str(mod)) or []) == [1, 2]


# ---------------------------------------------------------------------------
# Negative control: the failure scripts/ci/combine_pin_coverage.py exists to
# avoid. Before this script, the workflow attempted a bare `coverage combine`
# across the main and pin data files; that fails whenever the main run holds
# statement data and a pin holds branch data, which is exactly the state the
# workflow now always produces. This proves the restriction still holds
# against the installed coverage version, so a future coverage.py upgrade
# that quietly relaxed it would be caught here rather than assumed.
# ---------------------------------------------------------------------------
def test_negative_control_bare_coverage_combine_rejects_mixed_branch_and_statement_data(
    tmp_path: Path,
) -> None:
    mod = tmp_path / "mod.py"
    mod.write_text("def f(x):\n    if x:\n        return 1\n    return 2\n")
    branch_file = tmp_path / ".coverage.branch"
    statement_file = tmp_path / ".coverage.statement"
    _write_arc_data(branch_file, mod, [(-1, 1), (1, 2), (2, 3), (3, -1)])
    _write_line_data(statement_file, mod, [1, 2, 3, 4])

    # This test itself runs under pytest-cov when "Run pytest" collects this
    # file, with COVERAGE_FILE set to the real job's live main data file. The
    # child `coverage combine` below MUST NOT inherit that: `coverage combine
    # <paths>` writes its result to --data-file / COVERAGE_FILE (defaulting
    # to '.coverage'), not to the given paths, so an inherited COVERAGE_FILE
    # would make this subprocess merge into (and thereby corrupt) the parent
    # test session's own in-progress coverage data. --data-file pins the
    # destination explicitly; the env override is defense in depth for the
    # same reason.
    negative_control_output = tmp_path / ".coverage.negative-control-output"
    env = dict(os.environ)
    env["COVERAGE_FILE"] = str(negative_control_output)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "combine",
            f"--data-file={negative_control_output}",
            str(statement_file),
            str(branch_file),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode != 0, "mixed branch/statement data must not combine silently"
    assert "Can't combine" in result.stdout
