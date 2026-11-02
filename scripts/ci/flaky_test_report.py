#!/usr/bin/env python3
"""Detect flaky tests in a failed CI pytest leg, without masking the failure.

A leg in `.github/workflows/pytest.yml` that fails runs this twice.

``rerun`` reruns only the first run's failed tests once, serially, with a
separate cache and JUnit report (``scripts/ci/_flaky_rerun.py``). Above
``--max-tests`` failures it skips the rerun.

``report`` classifies each first-run failure (``scripts/ci/_flaky_classify.py``).
It writes a markdown table to ``GITHUB_STEP_SUMMARY``, a ``::warning`` per flaky
test, and a JSON report. It exits nonzero whenever the first run failed, flaky
or not: this is detection only, and a flake must stay visible.

EXIT CODES (ADR-035):
  0  - ``rerun``: state written (any test outcome, or a skipped rerun).
       ``report``: the first run passed and recorded no failure.
  1  - ``report``: the first run failed (always, even when every failure was
       flaky), or the rerun was skipped above the cap.
  2  - Config: bad arguments, or a state file this script did not write.
  3  - External: a missing or malformed JUnit report or cache file, or a rerun
       that cannot be classified. The last case covers a rerun that did not
       finish, exited 2 (a collection error or an interrupt, where pytest
       blames the module instead of the test), ran fewer tests than failed, or
       disagreed between its JUnit failure count and its cache.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.ci import (
        _flaky_classify,
        _flaky_inputs,
        _flaky_render,
        _flaky_rerun,
        _flaky_state,
        run_pytest_non_tmp,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised via direct file execution
    sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts.ci import (
        _flaky_classify,
        _flaky_inputs,
        _flaky_render,
        _flaky_rerun,
        _flaky_state,
        run_pytest_non_tmp,
    )

fs = _flaky_state

LASTFAILED_RELATIVE = Path(".pytest_cache") / "v" / "cache" / "lastfailed"
DEFAULT_MAX_TESTS = 25


def _load_inputs(
    first_junit: Path, out_dir: Path
) -> tuple[_flaky_inputs.JunitCounts, dict[str, object] | None, _flaky_inputs.JunitCounts | None]:
    """Load the first run's counts, the rerun state, and the rerun's counts."""
    first = _flaky_inputs.load_junit_counts(first_junit)
    state = fs.load_state(out_dir / fs.STATE_FILE)
    rerun_path = out_dir / fs.RERUN_JUNIT_FILE
    rerun = None
    if state is not None and state["status"] == fs.STATUS_RAN and rerun_path.is_file():
        rerun = _flaky_inputs.load_junit_counts(rerun_path)
    return first, state, rerun


def run_report(first_junit: Path, first_outcome: str, out_dir: Path, partition: str) -> int:
    """Classify the leg, write the summary and JSON report, return the exit code."""
    report_path = out_dir / fs.REPORT_FILE
    try:
        first, state, rerun = _load_inputs(first_junit, out_dir)
        outcome = _flaky_classify.classify(first, first_outcome, state, rerun)
    except (_flaky_inputs.InputError, fs.StateError) as exc:
        print(f"::error title=Flaky test report::{exc}")
        fs.write_json(report_path, {"partition": partition, "verdict": "error", "error": str(exc)})
        return fs.EXIT_CONFIG if isinstance(exc, fs.StateError) else fs.EXIT_EXTERNAL

    nodeids = fs.string_list(state, "first_failures") if state is not None else []
    for nodeid in outcome.flaky:
        escaped = _flaky_render.command_value(nodeid)
        print(f"::warning title=Flaky test::{escaped} failed, then passed on rerun")
    # The headline can quote a node id from the rerun cache, and stdout is the
    # runner's workflow-command channel, so it is escaped on the way out too.
    print(_flaky_render.command_value(outcome.headline))
    fs.write_json(
        report_path,
        {
            "partition": partition,
            "first_run_outcome": first_outcome,
            "first_run_failed": first.failed,
            "first_run_tests": first.tests,
            "rerun_status": state["status"] if state is not None else None,
            "flaky": outcome.flaky,
            "consistent": outcome.consistent,
            "unclassified": outcome.unclassified,
            "exit_code": outcome.exit_code,
        },
    )
    if outcome.exit_code == fs.EXIT_OK:
        return fs.EXIT_OK
    note = _flaky_render.cache_note(first, nodeids)
    # A summary write failure is logged as ::error by emit_summary; the exit
    # code is already nonzero here, so the step stays red either way.
    _flaky_render.emit_summary(_flaky_render.render_summary(partition, outcome, note))
    return outcome.exit_code


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    """Build the two-subcommand parser."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    rerun = sub.add_parser("rerun", help="Rerun the first run's failed tests once.")
    rerun.add_argument("--out-dir", type=Path, required=True)
    rerun.add_argument("--lastfailed", type=Path, default=_PROJECT_ROOT / LASTFAILED_RELATIVE)
    rerun.add_argument("--max-tests", type=_positive_int, default=DEFAULT_MAX_TESTS)

    report = sub.add_parser("report", help="Classify flaky tests and write the summary.")
    report.add_argument("--first-junit", type=Path, required=True)
    report.add_argument(
        "--first-outcome", choices=["success", "failure", "cancelled", "skipped"], required=True
    )
    report.add_argument("--out-dir", type=Path, required=True)
    report.add_argument("--partition", required=True)
    return parser


def main(argv: list[str] | None = None, runner: _flaky_rerun.PytestRunner | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return fs.EXIT_OK if exc.code == 0 else fs.EXIT_CONFIG
    try:
        if args.command == "rerun":
            chosen = runner if runner is not None else run_pytest_non_tmp.main
            return _flaky_rerun.run_rerun(args.lastfailed, args.out_dir, args.max_tests, chosen)
        return run_report(args.first_junit, args.first_outcome, args.out_dir, args.partition)
    except (_flaky_inputs.InputError, OSError) as exc:
        print(f"::error title=Flaky test report::{exc}")
        return fs.EXIT_EXTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
