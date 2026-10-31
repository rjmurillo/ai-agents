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
Passing only one of them, or an empty value, is a config error (exit 2).

``--breach-policy consecutive-main`` applies the owner decision of issue #6796.
One sample on a shared runner swings 2x to 4x, and the swing lands on a
different module each run. The regression of a module (or the suite) then fails
a push to main only when the same name also regressed on the previous main
run (``scripts/ci/consecutive_breach.py``). A first regression on main
warns and is recorded; an unknown previous run counts as a regression. Every
other event or ref warns. The policy reads the event and ref from ``--event``
and ``--ref``, else from GITHUB_EVENT_NAME and GITHUB_REF, and exits 2 when
either is missing. The default policy, ``strict``, keeps the contract above.

Exit codes: 0 ok (no regression, no baseline yet, or an advisory run), 1 logic
(a regression on an enforced run, or no test records), 2 config (bad arguments,
or a report declaring a DTD or entity), 3 external (unreadable input, or an
output or breach record that cannot be written).
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

from scripts.ci import consecutive_breach  # noqa: E402
from scripts.testing import duration_history, duration_render  # noqa: E402
from scripts.testing.duration_compare import Regression, Thresholds, compare  # noqa: E402
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
    parser.add_argument(
        "--write-history",
        type=Path,
        metavar="PATH",
        help="Append this snapshot to the history and write it here.",
    )
    parser.add_argument(
        "--max-history",
        type=int,
        default=30,
        help="Snapshots kept by --write-history (default: 30).",
    )
    parser.add_argument(
        "--sha", help="Commit this run measured (default: GITHUB_SHA under a breach policy)."
    )
    parser.add_argument("--summary", type=Path, help="Append the markdown report here.")
    parser.add_argument("--snapshot-out", type=Path, help="Write this run's snapshot JSON here.")
    parser.add_argument("--top", type=int, default=15, help="Slowest modules listed.")
    parser.add_argument("--module-ratio", type=_positive, default=1.5)
    parser.add_argument("--module-min-delta", type=_positive, default=10.0)
    parser.add_argument("--suite-ratio", type=_positive, default=1.25)
    parser.add_argument("--suite-min-delta", type=_positive, default=60.0)
    parser.add_argument("--event", help="Event that started the run (GITHUB_EVENT_NAME).")
    parser.add_argument("--ref", help="Ref the run measured (GITHUB_REF).")
    consecutive_breach.add_policy_arguments(parser, already_defined=("--event", "--ref", "--sha"))
    return parser


GATE = "duration-trend"
ENFORCED_EVENT = "push"
ENFORCED_REF = "refs/heads/main"


def is_enforced(event: str | None, ref: str | None) -> bool:
    """True when a regression fails the run: a push to main, or no run named.

    Raises ValueError when only one of ``event`` and ``ref`` is given, or when
    either is empty or blank. Such a run names no event, so treating it as
    advisory would let a missing CI variable mute the gate.
    """
    if event is None and ref is None:
        return True
    if event is None or ref is None:
        raise ValueError("--event and --ref must be given together")
    if not event.strip() or not ref.strip():
        raise ValueError("--event and --ref must not be empty")
    return event == ENFORCED_EVENT and ref == ENFORCED_REF


def _write_outputs(
    args: argparse.Namespace, snapshot: Snapshot, history: list[Snapshot], report: str
) -> None:
    """Write the data files first, so a summary never appears for a failed write."""
    if args.snapshot_out:
        duration_history.write_snapshot(args.snapshot_out, snapshot)
    if args.write_history:
        duration_history.write_history(args.write_history, [*history, snapshot], args.max_history)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(report)


def _advisory_note(event: str | None, ref: str | None) -> str:
    return (
        f"\nAdvisory run ({event} on {ref}): only a push to "
        f"`{ENFORCED_REF}` fails on a duration regression.\n"
    )


def _print_advisory(event: str | None, ref: str | None) -> None:
    print(
        f"duration: advisory on event={event} ref={ref}; only a push to "
        f"{ENFORCED_REF} fails on a regression",
        file=sys.stderr,
    )


def _report_note(
    args: argparse.Namespace, policy: consecutive_breach.Policy, regressed: int
) -> str:
    """The closing line of the markdown report, naming why a regression may not fail."""
    if not regressed:
        return ""
    if policy.name == consecutive_breach.POLICY_STRICT:
        return "" if is_enforced(args.event, args.ref) else _advisory_note(args.event, args.ref)
    if policy.mode == consecutive_breach.MODE_CONSECUTIVE:
        return (
            f"\nPush to `{ENFORCED_REF}`: a regression fails the run only when the same "
            "name also regressed on the previous main run, or that run cannot be established "
            "(issue #6796).\n"
        )
    return _advisory_note(policy.event, policy.ref)


def _strict_verdict(args: argparse.Namespace, regressed: int) -> int:
    """The pre-policy contract: any regression fails an enforced run (issue #6244)."""
    if not regressed or is_enforced(args.event, args.ref):
        return 1 if regressed else 0
    _print_advisory(args.event, args.ref)
    return 0


def _apply_policy(regressions: Sequence[Regression], policy: consecutive_breach.Policy) -> int:
    """Warn or fail per the policy. A main run also writes its breach record."""
    breaches = {r.name: duration_render.regression_text(r) for r in regressions}
    try:
        verdict = consecutive_breach.apply_policy(
            GATE, breaches, policy, title="Test duration trend"
        )
    except OSError as exc:
        print(
            consecutive_breach.annotation(
                "error", "Test duration trend", f"could not write the breach record: {exc}"
            )
        )
        return 3
    if policy.mode == consecutive_breach.MODE_ADVISORY and regressions:
        _print_advisory(policy.event, policy.ref)
    return 1 if verdict.failing else 0


def _run_identity_ok(args: argparse.Namespace) -> bool:
    """False, with a message, when --event and --ref are partial or empty."""
    try:
        is_enforced(args.event, args.ref)
    except ValueError as exc:
        print(f"bad run identity: {exc}", file=sys.stderr)
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.max_history < 1 or args.top < 1:
        print("--max-history and --top must be at least 1", file=sys.stderr)
        return 2
    try:
        policy = consecutive_breach.policy_from_args(args)
    except ValueError as exc:
        print(f"bad breach policy: {exc}", file=sys.stderr)
        return 2
    if policy.name == consecutive_breach.POLICY_STRICT and not _run_identity_ok(args):
        return 2
    try:
        snapshot = build_snapshot(args.inputs, args.sha or policy.sha, datetime.now(UTC))
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
    limits = Thresholds(
        args.module_ratio, args.module_min_delta, args.suite_ratio, args.suite_min_delta
    )
    comparison = compare(snapshot, history, limits)
    report = duration_render.render_markdown(snapshot, history, comparison, args.top, note)
    regressions = duration_render.regressions_of(comparison)
    regressed = len(regressions)
    report += _report_note(args, policy, regressed)
    try:
        _write_outputs(args, snapshot, history, report)
    except OSError as exc:
        print(f"::error title=Test duration report::could not write output: {exc}")
        return 3
    print(report)
    print(
        f"duration: {regressed} regressions in {comparison.comparable} comparable "
        f"modules, {len(snapshot.modules)} modules measured",
        file=sys.stderr,
    )
    if policy.name != consecutive_breach.POLICY_STRICT:
        return _apply_policy(regressions, policy)
    for line in duration_render.warning_commands(comparison):
        print(line)
    return _strict_verdict(args, regressed)


if __name__ == "__main__":
    sys.exit(main())
