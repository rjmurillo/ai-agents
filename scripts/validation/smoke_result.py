#!/usr/bin/env python3
"""Report the CLI smoke result from the upstream job results.

The summary job of ``.github/workflows/plugin-cli-smoke.yml`` runs this from
the base commit with ``python -I`` (ADR-006: no logic in YAML). It is stdlib-only.
The ``--check`` core forks ``scripts/ci/require_job_results.py``, kept separate so
that shared script is unchanged for other workflows; merge the two later.

A check is ``NAME EXPECTED MESSAGE``: NAME is an environment variable the
workflow filled from a ``needs.*`` expression. MESSAGE prints as an ``::error::``
annotation, with ``{value}`` replaced by the observed value. Every check runs,
so one run reports all failures. An unset variable reads as the empty string and
fails its check. A failing ``failure``, ``cancelled``, or ``skipped`` value also
names the variable, the likely cause, and the next action.

``--skippable-check`` takes the same arguments and is not evaluated when
``--skip-when NAME VALUE`` matches; that needs at least one ``--check``.
``--guarded-check GUARD_NAME GUARD_VALUE NAME EXPECTED MESSAGE`` is skippable
and also not evaluated unless GUARD_NAME equals GUARD_VALUE, so a message that
blames a downstream cause stays quiet when the upstream job it needs failed.
``--skip-message`` prints instead of ``--success-message`` after a skip.

``--preset NAME`` expands to a stored argument list (``PRESETS``) placed before
any other flags, so the workflow stays a one-line call (ADR-006).

Exit codes (ADR-035): 0 every check matched, 1 a check failed, 2 usage.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence

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

# The plugin-cli-smoke.yml summary gate, as the generic flags it replaced.
_PLUGIN_CLI_SMOKE = (
    *("--check", "CHANGES_RESULT", "success", "Smoke path filter result: {value}"),
    *("--skip-when", "RUN", "false"),
    *("--skip-message", "No smoke path changed; CLI smoke legs skipped."),
    *("--skippable-check", "AUTHORIZE_RESULT", "success", "Trusted-context gate result: {value}"),
    *(
        "--guarded-check",
        *("AUTHORIZE_RESULT", "success", "TRUSTED", "true"),
        "Untrusted context: this change touches smoke paths from a fork pull request or a "
        "non-default ref. Forks get no secrets, so the CLI smoke cannot run. A maintainer "
        "must rerun it from a same-repo branch.",
    ),
    *("--skippable-check", "CODEX_RESULT", "success", "Codex smoke result: {value}"),
    *(
        "--skippable-check",
        *("HOOKS_RESULT", "success", "Claude hook discovery smoke result: {value}"),
    ),
    *("--skippable-check", "PI_RESULT", "success", "Pi smoke result: {value}"),
    *("--success-message", "CLI smoke passed for every leg that ran."),
)
PRESETS = {"plugin-cli-smoke": _PLUGIN_CLI_SMOKE}


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    names = ("NAME", "EXPECTED", "MESSAGE")
    for flag, text in (
        ("--check", "Variable, value, message."),
        ("--skippable-check", "Like --check."),
    ):
        parser.add_argument(flag, nargs=3, action="append", metavar=names, help=text)
    parser.add_argument(
        "--guarded-check",
        nargs=5,
        action="append",
        metavar=("GUARD_NAME", "GUARD_VALUE", *names),
        help="Like --skippable-check, evaluated only when GUARD_NAME equals GUARD_VALUE.",
    )
    parser.add_argument("--preset", choices=sorted(PRESETS), help="Stored flag set.")
    parser.add_argument("--skip-when", nargs=2, metavar=("NAME", "VALUE"))
    parser.add_argument("--skip-message", default="", help="Printed when the skip held.")
    parser.add_argument("--success-message", default="", help="Printed when all matched.")
    return parser


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
    parser = _build_parser()
    given = sys.argv[1:] if argv is None else argv
    args = parser.parse_args([*PRESETS.get(parser.parse_args(given).preset, ()), *given])
    always = [tuple(c) for c in args.check or []]
    skippable = [tuple(c) for c in args.skippable_check or []]
    problem = _usage_problem(args, always, skippable)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return EXIT_USAGE

    skipping = bool(args.skip_when) and os.environ.get(args.skip_when[0]) == args.skip_when[1]
    guarded = [tuple(c[2:]) for c in args.guarded_check or [] if os.environ.get(c[0]) == c[1]]
    bad = failing_checks(always if skipping else always + skippable + guarded, os.environ)
    for line in bad:
        print(f"::error::{line}")
    if bad:
        return EXIT_MISMATCH
    if skipping:
        if args.skip_message:
            print(args.skip_message)
    elif args.success_message:
        print(args.success_message)
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
