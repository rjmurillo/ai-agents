#!/usr/bin/env python3
"""Report the CLI smoke result from the upstream job results.

The summary job of ``.github/workflows/plugin-cli-smoke.yml`` runs this from
the base commit with ``python -I``. Keeping the comparison here (ADR-006: no
logic in YAML) makes the gate testable. It is stdlib-only.

A check is ``NAME EXPECTED MESSAGE``: NAME is an environment variable the
workflow filled from a ``needs.*`` expression. MESSAGE is printed as an
``::error::`` annotation, with ``{value}`` replaced by the observed value.
Every check runs, so one run reports all failures. An unset variable reads as
the empty string and fails its check: a summary job that cannot see an upstream
result must not report success.

``--skippable-check`` takes the same arguments and is not evaluated when
``--skip-when NAME VALUE`` matches. ``--skip-message`` is printed instead of
``--success-message`` after every ``--check`` passed. ``--skip-when`` needs at
least one ``--check``, so a skip never bypasses every check.

A failing value of ``failure``, ``cancelled``, or ``skipped`` also names the
variable and gives the likely cause and next action.

``--count-dir DIR --count-message TEMPLATE`` replaces ``--success-message`` when
the integers in the files under DIR (one per line, a leg's quota-skip count)
sum above zero. ``{count}`` becomes the total. A missing DIR sums to zero.

Exit codes (ADR-035): 0 every check matched, 1 a check failed, 2 usage.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2

# Cause and next action per GitHub `needs.<job>.result` value. A matrix job
# reports one aggregate value, so the hint points at the failing leg.
_RESULT_HINTS = {
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


def failing_checks(checks: Sequence[tuple[str, str, str]], environ: Mapping[str, str]) -> list[str]:
    """Return one annotation per mismatched check, with a hint for known results."""
    lines = []
    for name, expected, message in checks:
        value = environ.get(name, "")
        if value == expected:
            continue
        line = message.replace("{value}", value)
        hint = _RESULT_HINTS.get(value)
        lines.append(f"{line} [{name}={value}] {hint}" if hint else line)
    return lines


def sum_counts(count_dir: Path) -> int:
    """Sum the integers of every file under ``count_dir``; warn on a bad line."""
    total = 0
    paths = sorted(p for p in count_dir.rglob("*") if p.is_file()) if count_dir.is_dir() else []
    for path in paths:
        for token in path.read_text(encoding="utf-8").split():
            try:
                total += int(token)
            except ValueError:
                print(f"::warning::ignoring non-integer count {token!r} in {path}")
    return total


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    names = ("NAME", "EXPECTED", "MESSAGE")
    parser.add_argument(
        "--check", nargs=3, action="append", metavar=names, help="Variable, value, message."
    )
    parser.add_argument(
        "--skippable-check", nargs=3, action="append", metavar=names, help="Like --check."
    )
    parser.add_argument("--skip-when", nargs=2, metavar=("NAME", "VALUE"))
    parser.add_argument("--skip-message", default="", help="Printed when the skip held.")
    parser.add_argument("--success-message", default="", help="Printed when all matched.")
    parser.add_argument("--count-dir", type=Path, help="Directory of quota-skip counts.")
    parser.add_argument("--count-message", default="", help="Uses {count}; needs --count-dir.")
    return parser


def _success_text(args: argparse.Namespace) -> str:
    total = sum_counts(args.count_dir) if args.count_dir and args.count_message else 0
    count_message: str = args.count_message
    success_message: str = args.success_message
    return count_message.replace("{count}", str(total)) if total > 0 else success_message


def _usage_problem(
    args: argparse.Namespace, always: list[tuple[str, ...]], skippable: list[tuple[str, ...]]
) -> str | None:
    if not always and not skippable:
        return "at least one --check is required"
    if args.skip_when and not always:
        return "--skip-when needs at least one --check"
    return None


def main(argv: list[str] | None = None) -> int:
    """Evaluate every check. Returns an ADR-035 exit code."""
    args = _build_parser().parse_args(argv)
    always = [tuple(c) for c in args.check or []]
    skippable = [tuple(c) for c in args.skippable_check or []]
    problem = _usage_problem(args, always, skippable)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return EXIT_USAGE

    skipping = bool(args.skip_when) and os.environ.get(args.skip_when[0]) == args.skip_when[1]
    bad = failing_checks(always if skipping else always + skippable, os.environ)
    for line in bad:
        print(f"::error::{line}")
    if bad:
        return EXIT_MISMATCH
    final = args.skip_message if skipping else _success_text(args)
    if final:
        print(final)
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
