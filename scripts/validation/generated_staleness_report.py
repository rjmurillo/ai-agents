"""Parse the stale-path report ``build_all.py --check`` prints on failure.

Split out of ``check_generated_staleness.py`` to keep that gate under the taste
file-size ceiling (issue #6427). Standard library only, so the gate can import
it without widening its dependency surface.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

# How many stale paths the failure summary names. The child lists every one, so
# a 306-path regeneration pushes the header and the first 266 paths past the
# 40-line tail (issue #6427); the summary restores the head.
MAX_STALE_PATHS_SHOWN = 10

# Output contract of the child, ``build/scripts/build_all.py`` ``--check``. The
# header opens a block of two-space-indented paths; the other two kinds are one
# path per line; the marker line is the commit-or-regenerate remedy. The marker
# is generated from ``build_all.UNCOMMITTEDUNCHANGED_PREFIX`` and
# ``tests/validation/test_check_generated_staleness_evidence.py`` fails when the two
# spellings differ.
DRIFT_HEADER = "STALENESS DETECTED: uncommitted regen drift:"
_STALE_ITEM = re.compile(r"^STALENESS DETECTED: [^:]+: (?P<item>\S.*)$")
UNCHANGED_PREFIX = "UNCOMMITTED BUT UNCHANGED BY REGENERATION:"
_UNCHANGED_COUNTS = re.compile(rf"^{re.escape(UNCHANGED_PREFIX)} (\d+) of (\d+) ")
_DRIFT_PATH = re.compile(r"^  (?P<path>\S.*)$")


@dataclass(frozen=True, slots=True)
class StaleReport:
    """What a failed ``build_all.py --check`` said, split by role.

    ``paths`` are the stale paths in the order the child listed them. ``hint``
    is the child's commit-or-regenerate line, empty when it printed none.
    ``uncommitted_only`` is true when the hint says every drifted path is
    uncommitted and unchanged by regeneration. ``other`` is every line that is
    neither, so the diagnosis of a non-staleness failure survives the filter.
    """

    paths: tuple[str, ...] = ()
    hint: str = ""
    uncommitted_only: bool = False
    other: tuple[str, ...] = ()


def parse_stale_report(output: str) -> StaleReport:
    """Split the child's combined output into stale paths, hint, and the rest.

    Only the drift block is consumed as paths: generator progress lines are
    also indented, so the indented-path rule applies from the header until the
    first line that is not indented, never to the output at large.
    """
    paths: list[str] = []
    other: list[str] = []
    hint = ""
    uncommitted_only = False
    in_block = False
    for line in output.splitlines():
        in_block = in_block and _DRIFT_PATH.match(line) is not None
        if in_block:
            paths.append(line.strip())
        elif line.strip() == DRIFT_HEADER:
            in_block = True
        elif line.startswith(UNCHANGED_PREFIX):
            hint = line.strip()
            counts = _UNCHANGED_COUNTS.match(line)
            uncommitted_only = counts is not None and counts.group(1) == counts.group(2)
        elif (item := _STALE_ITEM.match(line)) is not None:
            paths.append(item.group("item").strip())
        else:
            other.append(line)
    return StaleReport(tuple(paths), hint, uncommitted_only, tuple(other))


def echo_stale_summary(report: StaleReport) -> None:
    """Print the stale count, the first paths, and the child's remedy line.

    The head of the list, not the tail: ``_echo_tail`` keeps the last lines, so
    on a large regeneration the first stale paths and the header are exactly
    what it omits. The remedy line is repeated here because the tail drops it
    when it is not among the last lines.
    """
    if not report.paths:
        return
    shown = report.paths[:MAX_STALE_PATHS_SHOWN]
    hidden = len(report.paths) - len(shown)
    print(f"[STALE] {len(report.paths)} generated path(s) differ from HEAD; first {len(shown)}:")
    for path in shown:
        print(f"  {path}")
    if hidden:
        print(f"  ... and {hidden} more")
    if report.hint:
        print(report.hint)
    sys.stdout.flush()


def failure_detail(report: StaleReport) -> str:
    """Return the one-paragraph evidence the pre-PR summary prints for a FAIL."""
    if not report.paths:
        return (
            "build_all.py --check failed without listing stale paths; read the"
            " check output above for the cause."
        )
    shown = report.paths[:MAX_STALE_PATHS_SHOWN]
    more = len(report.paths) - len(shown)
    listed = ", ".join(shown) + (f", and {more} more" if more else "")
    detail = f"{len(report.paths)} generated path(s) differ from HEAD: {listed}."
    return f"{detail} {report.hint}" if report.hint else detail


def remedy(report: StaleReport) -> str:
    """Return the remedy text for a failed child, by what it reported."""
    if report.uncommitted_only:
        return (
            "Every drifted path is uncommitted and already matches the generators."
            " Commit the regenerated files, then rerun this gate."
        )
    return (
        "Read the check's output above for the cause. If it reports"
        " staleness or drift, regenerate and commit:\n"
        "  uv run python build/scripts/build_all.py\n"
        "Otherwise fix the error the check itself reported; regenerating"
        " is not the remedy for a configuration or source failure."
    )
