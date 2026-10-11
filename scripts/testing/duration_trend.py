"""Test duration trend and regression report.

Reads the JUnit reports the pytest partitions already wrote, turns them into a
snapshot of seconds per test module and wall seconds per partition, and compares
that snapshot with a rolling history of earlier snapshots from main::

    uv run python scripts/testing/duration_trend.py artifacts/pytest-results*.xml \\
        --history history.json --summary "$GITHUB_STEP_SUMMARY"

A module regresses when it is both ``--module-ratio`` times slower and
``--module-min-delta`` seconds slower than its median baseline. The suite
regresses when the sum over comparable modules crosses the ``--suite-ratio``
and ``--suite-min-delta`` pair. ``duration_compare.py`` defines "comparable".

``--write-history`` appends this run's snapshot to the history, keeping the
newest ``--max-history`` entries. It may name the same file as ``--history``.

A regression fails the run only on a push to main. ``--event`` and ``--ref``
name the run; any other event or ref, such as a pull request, reports the
regression as a warning and exits 0, because runner timing noise must not block
a merge (issue #6244). With neither flag the run is enforced, as on main.
Passing only one of them makes the run advisory.

Exit codes: 0 ok (no regression, no baseline yet, or an advisory run), 1 logic
(a regression on an enforced run, or no test records), 2 config (bad arguments,
or a report declaring a DTD or entity), 3 external (unreadable input, or an
output that cannot be written).
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

# Bootstrap the repository root so a bare `python3 scripts/testing/duration_trend.py`
# resolves the sibling imports, same pattern as `slow_test_budget.py`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.testing import duration_history, duration_render  # noqa: E402
from scripts.testing.duration_compare import Thresholds, compare  # noqa: E402
from scripts.testing.duration_snapshot import Snapshot, build_snapshot  # noqa: E402


def _positive(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"{value} is not positive")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report test durations against main history.")
    parser.add_argument("inputs", nargs="+", type=Path, help="pytest JUnit XML reports.")
    parser.add_argument("--history", type=Path, help="History JSON to compare against.")
    parser.add_argument("--write-history", type=Path, metavar="PATH",
                        help="Append this snapshot to the history and write it here.")
    parser.add_argument("--max-history", type=int, default=30,
                        help="Snapshots kept by --write-history (default: 30).")
    parser.add_argument("--sha", default="unknown", help="Commit this run measured.")
    parser.add_argument("--summary", type=Path, help="Append the markdown report here.")
    parser.add_argument("--snapshot-out", type=Path, help="Write this run's snapshot JSON here.")
    parser.add_argument("--top", type=int, default=15, help="Slowest modules listed.")
    parser.add_argument("--module-ratio", type=_positive, default=1.5)
    parser.add_argument("--module-min-delta", type=_positive, default=10.0)
    parser.add_argument("--suite-ratio", type=_positive, default=1.25)
    parser.add_argument("--suite-min-delta", type=_positive, default=60.0)
    parser.add_argument("--event", help="Event that started the run (GITHUB_EVENT_NAME).")
    parser.add_argument("--ref", help="Ref the run measured (GITHUB_REF).")
    return parser


ENFORCED_EVENT = "push"
ENFORCED_REF = "refs/heads/main"


def is_enforced(event: str | None, ref: str | None) -> bool:
    """True when a regression fails the run: a push to main, or no run named."""
    if event is None and ref is None:
        return True
    return event == ENFORCED_EVENT and ref == ENFORCED_REF


def _write_outputs(args: argparse.Namespace, snapshot: Snapshot,
                   history: list[Snapshot], report: str) -> None:
    """Write the data files first, so a summary never appears for a failed write."""
    if args.snapshot_out:
        duration_history.write_snapshot(args.snapshot_out, snapshot)
    if args.write_history:
        duration_history.write_history(args.write_history, [*history, snapshot],
                                        args.max_history)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(report)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.max_history < 1 or args.top < 1:
        print("--max-history and --top must be at least 1", file=sys.stderr)
        return 2
    try:
        snapshot = build_snapshot(args.inputs, args.sha, datetime.now(UTC))
    except (OSError, ET.ParseError) as exc:
        print(f"could not read input: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"malformed input: {exc}", file=sys.stderr)
        return 2
    if not snapshot.modules:
        print("no test records in the given inputs", file=sys.stderr)
        return 1
    history, note = duration_history.load_history(args.history)
    limits = Thresholds(args.module_ratio, args.module_min_delta,
                        args.suite_ratio, args.suite_min_delta)
    comparison = compare(snapshot, history, limits)
    report = duration_render.render_markdown(snapshot, history, comparison, args.top, note)
    regressed = len(comparison.modules) + (1 if comparison.suite else 0)
    advisory = bool(regressed) and not is_enforced(args.event, args.ref)
    if advisory:
        report += (f"\nAdvisory run ({args.event} on {args.ref}): only a push to "
                   f"`{ENFORCED_REF}` fails on a duration regression.\n")
    try:
        _write_outputs(args, snapshot, history, report)
    except OSError as exc:
        print(f"::error title=Test duration report::could not write output: {exc}")
        return 3
    print(report)
    for line in duration_render.warning_commands(comparison):
        print(line)
    print(f"duration: {regressed} regressions in {comparison.comparable} comparable "
          f"modules, {len(snapshot.modules)} modules measured", file=sys.stderr)
    if not advisory:
        return 1 if regressed else 0
    print(f"duration: advisory on event={args.event} ref={args.ref}; only a push to "
          f"{ENFORCED_REF} fails on a regression", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
