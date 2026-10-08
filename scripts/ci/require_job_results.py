#!/usr/bin/env python3
"""Assert that upstream job results match their expected values.

Replaces the inline shell chain in a workflow's summary job, which read each
`needs.<job>.result` (or an output) from the environment, compared it to an
expected string, emitted a `::error::` annotation, and exited 1 on the first
mismatch. Keeping the comparison here (ADR-006: no logic in YAML) makes the
gate testable.

Every check is evaluated so a single run reports all failures, not just the
first. The exit code is 1 if any check failed.

A check is `NAME EXPECTED MESSAGE`, where NAME is an environment variable the
workflow populated from a `needs.*` expression. MESSAGE is emitted verbatim
unless it contains `{value}`, which is replaced with the observed value.

A check can also be skippable. `--skippable-check NAME EXPECTED MESSAGE` is
evaluated like `--check` unless the run matches `--skip-when NAME VALUE`, in
which case it is not evaluated and `--skip-message` is printed after every
`--check` passed. A path-filtered workflow uses this so a run that needed no
legs reports success, while a failed filter job still fails. `--skip-when`
requires at least one `--check`, so a skip can never bypass every check.

When a failing value is `failure`, `cancelled`, or `skipped`, the error line also
names the variable and appends the likely cause and the next action, so a red
summary job says where to look. Other values keep the bare message.

`--count-dir DIR --count-message TEMPLATE` adds an observability note to a run
that passed. Every file under DIR holds one integer per line (a leg's count of
quota-skipped checks). When the total is above zero, TEMPLATE replaces
`--success-message`, with `{count}` replaced by the total. A missing or empty DIR
reads as zero. Both flags are optional, so existing callers are unchanged.

An unset variable reads as the empty string and therefore fails its check.
That is deliberate: a summary job that cannot see an upstream result must not
report success.

EXIT CODES (ADR-035):
  0  - Success: every check matched
  1  - Error: at least one check did not match
  2  - Error: usage/configuration (no checks supplied)
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2


def _format(message: str, value: str) -> str:
    """Return MESSAGE with `{value}` replaced, or unchanged when absent."""
    if "{value}" not in message:
        return message
    return message.replace("{value}", value)


# Cause and next action per GitHub `needs.<job>.result` value. A matrix job
# reports one aggregate value, so the hint points at the failing leg.
_RESULT_HINTS: Mapping[str, str] = {
    "failure": (
        "Cause: a job or matrix leg failed. An environment approval that was "
        "rejected or timed out also reports as a failure. "
        "Next: open the failing job in this run and read its first red step."
    ),
    "cancelled": (
        "Cause: a newer push superseded this run, or it was cancelled by hand. "
        "Next: re-run the jobs, or check the latest run for this branch."
    ),
    "skipped": (
        "Cause: a job this one needs did not run, usually because an earlier job "
        "failed or its condition was false. Next: check the jobs listed in `needs`."
    ),
}


def _with_hint(name: str, value: str, message: str) -> str:
    """Append the variable name and a cause and next action for a known result value."""
    hint = _RESULT_HINTS.get(value)
    if hint is None:
        return message
    return f"{message} [{name}={value}] {hint}"


def failing_checks(
    checks: list[tuple[str, str, str]], environ: Mapping[str, str]
) -> list[tuple[str, str, str]]:
    """Return ``(name, observed value, formatted message)`` per mismatched check."""
    return [
        (name, environ.get(name, ""), _format(message, environ.get(name, "")))
        for name, expected, message in checks
        if environ.get(name, "") != expected
    ]


def failures(checks: list[tuple[str, str, str]], environ: Mapping[str, str]) -> list[str]:
    """Return one formatted message per check whose value did not match."""
    return [message for _name, _value, message in failing_checks(checks, environ)]


def sum_counts(count_dir: Path) -> int:
    """Sum the integers, one per line, of every file under ``count_dir``.

    A missing directory reads as zero. A line that is not an integer is reported
    as a warning and not counted, so one corrupt file cannot fail a passing run.
    """
    if not count_dir.is_dir():
        return 0
    total = 0
    for path in sorted(p for p in count_dir.rglob("*") if p.is_file()):
        for line in path.read_text(encoding="utf-8").split():
            try:
                total += int(line)
            except ValueError:
                print(f"::warning::ignoring non-integer count {line!r} in {path}")
    return total


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the job-result gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        nargs=3,
        action="append",
        metavar=("NAME", "EXPECTED", "MESSAGE"),
        help="Environment variable, its required value, and the failure message.",
    )
    parser.add_argument(
        "--skippable-check",
        nargs=3,
        action="append",
        metavar=("NAME", "EXPECTED", "MESSAGE"),
        help="Like --check, but not evaluated when --skip-when matches.",
    )
    parser.add_argument(
        "--skip-when",
        nargs=2,
        metavar=("NAME", "VALUE"),
        help="Skip the --skippable-check entries when NAME equals VALUE.",
    )
    parser.add_argument(
        "--skip-message",
        default="",
        help="Message to print when the skip condition held and every --check passed.",
    )
    parser.add_argument(
        "--success-message",
        default="",
        help="Message to print when every check matched.",
    )
    parser.add_argument(
        "--count-dir",
        type=Path,
        default=None,
        help="Directory of count files to sum when every check matched.",
    )
    parser.add_argument(
        "--count-message",
        default="",
        help="Printed instead of --success-message when the count total is above zero. "
        "Use {count} for the total. Requires --count-dir.",
    )
    return parser


def _skip_applies(skip_when: list[str] | None, environ: Mapping[str, str]) -> bool:
    """True when `--skip-when NAME VALUE` matches. An unset NAME never matches."""
    if not skip_when:
        return False
    name, value = skip_when
    return name in environ and environ[name] == value


def main(argv: list[str] | None = None) -> int:
    """Evaluate every check. Returns an ADR-035 exit code."""
    args = build_parser().parse_args(argv)

    always = [(name, expected, message) for name, expected, message in args.check or []]
    skippable = [
        (name, expected, message) for name, expected, message in args.skippable_check or []
    ]
    if not always and not skippable:
        print("ERROR: at least one --check is required", file=sys.stderr)
        return EXIT_USAGE
    if args.skip_when and not always:
        print("ERROR: --skip-when needs at least one --check", file=sys.stderr)
        return EXIT_USAGE

    skipping = _skip_applies(args.skip_when, os.environ)
    checks = always if skipping else [*always, *skippable]
    bad = failing_checks(checks, os.environ)
    for name, value, message in bad:
        print(f"::error::{_with_hint(name, value, message)}")
    if bad:
        return EXIT_MISMATCH

    final = args.skip_message if skipping else _success_text(args)
    if final:
        print(final)
    return EXIT_SUCCESS


def _success_text(args: argparse.Namespace) -> str:
    """Return the count message when counts are above zero, else the success message."""
    if args.count_dir is None or not args.count_message:
        return args.success_message
    total = sum_counts(args.count_dir)
    if total <= 0:
        return args.success_message
    return args.count_message.replace("{count}", str(total))


if __name__ == "__main__":
    sys.exit(main())
