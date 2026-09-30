#!/usr/bin/env python3
"""Report an advisory step's result as a typed line, without changing its exit code.

Issue #5636, decision D17 item 2. A workflow step with ``continue-on-error`` and
a lefthook job guarded by ``|| echo`` or ``ruff --exit-zero`` are advisory on
purpose: their failure must not block. Before this helper each one swallowed its
own failure and left only a raw log line, so no gate and no dashboard could
count how often an advisory step failed or why.

Two modes, both stdlib plus ``scripts.validation.evidence``. Each exits 0 on a
valid call, so the step keeps the semantics it had, except ``run`` with
``--propagate-errors`` (below):

``step``
    Reads the outcome GitHub records for an earlier step
    (``${{ steps.<id>.outcome }}``: ``success``, ``failure``, ``cancelled``, or
    ``skipped``) and prints one typed result. Use it after a step that carries
    ``continue-on-error``. ``outcome`` is the value before the swallow, which is
    why it is the input and ``conclusion`` is not.

``run``
    Runs a command with inherited output and prints one typed result from its
    exit code. Use it where a shell guard used to swallow the exit code. Exit
    codes named by ``--findings-exit`` mean findings (``FAIL`` with
    ``advisory.findings``); any other non-zero code is a tool error (``BLOCKED``
    with ``script.failed``). A missing executable is ``BLOCKED`` with
    ``tool.absent``, a timeout is ``BLOCKED`` with ``timeout``, and a signal
    death is ``BLOCKED`` with ``process.signaled``.

The typed line has the shape ``[STATE] validator reason=code scope=... detail=...``
that ``CheckOutcome.report_line`` prints, so one grep counts every advisory
non-pass. A non-pass also writes a ``::warning::`` annotation. Under GitHub
Actions the result is appended to the step summary and written to
``GITHUB_OUTPUT`` as ``state`` and ``reason``, so a later step or job can read
it. A ``PASS`` prints one line and no annotation.

An unrecognized outcome (empty because a step id was mistyped, or a value GitHub
adds later) is ``UNKNOWN`` with ``output.malformed``, never ``PASS``: a report
that cannot read its input must not certify it.

``run --propagate-errors`` keeps one distinction the old command had. Findings
still exit 0. A tool error does not: an exit code that is neither 0 nor a
findings code is returned as the child's own code, and a missing executable, a
timeout, or a signal death returns 3. Use it where the old command could fail
its job on a crash, such as ``ruff check --exit-zero``, whose exit code 2 (a
configuration error) still failed the hook. A crash of the linter must not read
as a passing lint.

EXIT CODES (ADR-035):
  0 - the report was produced (whatever the observed state); with
      ``--propagate-errors``, also only when the command found nothing or
      reported findings
  2 - bad arguments (an unknown state, a malformed reason code, no command)
  3 - ``run --propagate-errors`` and the command could not run or was killed
  N - ``run --propagate-errors`` and the command exited with its own error code N
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import (  # noqa: E402
    REASON_ADVISORY_FINDINGS,
    REASON_MALFORMED_OUTPUT,
    REASON_POLICY_EXEMPT,
    REASON_PROCESS_SIGNALED,
    REASON_SCRIPT_FAILED,
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
    CheckOutcome,
    EvidenceState,
)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
DEFAULT_TIMEOUT_SECONDS = 600
_REASON_SHAPE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
_NAME_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_FAILURE_STATES = ("FAIL", "BLOCKED", "UNKNOWN")


def _outcome_from_step(args: argparse.Namespace) -> CheckOutcome:
    """Map a recorded step outcome to a typed result."""
    name, scope, detail = args.validator, args.scope, args.detail
    if args.outcome == "success":
        return CheckOutcome.passed(name, revision=_revision(), scope=scope, detail=detail)
    if args.outcome == "skipped":
        return CheckOutcome.skipped(
            name, reason=REASON_POLICY_EXEMPT, scope=scope, detail="the step did not run"
        )
    if args.outcome in ("failure", "cancelled"):
        return _failure(args, detail or f"the step outcome was {args.outcome}")
    return CheckOutcome.unknown(
        name,
        reason=REASON_MALFORMED_OUTPUT,
        scope=scope,
        detail=f"unrecognized step outcome {args.outcome!r}; a mistyped step id reads as empty",
    )


def _failure(args: argparse.Namespace, detail: str) -> CheckOutcome:
    """Build the configured non-pass result for a failed step or command."""
    build = {
        "FAIL": CheckOutcome.failed,
        "BLOCKED": CheckOutcome.blocked,
        "UNKNOWN": CheckOutcome.unknown,
    }[args.failure_state]
    return build(args.validator, reason=args.failure_reason, scope=args.scope, detail=detail)


def _revision() -> str:
    return os.environ.get("GITHUB_SHA", "") or "WORKING_TREE"


def _run_command(args: argparse.Namespace) -> tuple[CheckOutcome, int]:
    """Run the wrapped command; return its typed result and the exit to propagate."""
    name, scope = args.validator, args.scope
    try:
        # The child inherits stdout. Flush first so output already buffered here
        # reaches the log before the child's, not after it.
        sys.stdout.flush()
        completed = subprocess.run(args.command, timeout=args.timeout, check=False)
    except FileNotFoundError:
        detail = f"{args.command[0]} not found"
        return CheckOutcome.blocked(
            name, reason=REASON_TOOL_ABSENT, scope=scope, detail=detail
        ), EXIT_EXTERNAL
    except subprocess.TimeoutExpired:
        detail = f"exceeded {args.timeout}s"
        return CheckOutcome.blocked(
            name, reason=REASON_TIMEOUT, scope=scope, detail=detail
        ), EXIT_EXTERNAL
    except OSError as exc:
        detail = f"could not start: {exc}"
        return CheckOutcome.blocked(
            name, reason=REASON_TOOL_ABSENT, scope=scope, detail=detail
        ), EXIT_EXTERNAL
    return _outcome_from_exit(args, completed.returncode), _propagated_code(
        args, completed.returncode
    )


def _propagated_code(args: argparse.Namespace, code: int) -> int:
    """Return the exit code ``--propagate-errors`` hands back for a finished command."""
    if code == 0 or code in args.findings_exit:
        return EXIT_OK
    return EXIT_EXTERNAL if code < 0 else code


def _outcome_from_exit(args: argparse.Namespace, code: int) -> CheckOutcome:
    name, scope = args.validator, args.scope
    if code == 0:
        return CheckOutcome.passed(name, revision=_revision(), scope=scope)
    if code < 0:
        return CheckOutcome.blocked(
            name, reason=REASON_PROCESS_SIGNALED, scope=scope, detail=f"killed by signal {-code}"
        )
    if code in args.findings_exit:
        return CheckOutcome.failed(
            name,
            reason=REASON_ADVISORY_FINDINGS,
            scope=scope,
            detail=f"exit {code}, findings reported",
        )
    return CheckOutcome.blocked(
        name, reason=REASON_SCRIPT_FAILED, scope=scope, detail=f"exit {code}, not a findings code"
    )


def _escape_annotation(text: str) -> str:
    """Escape a workflow-command message so a value cannot start a second command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _publish(outcome: CheckOutcome) -> None:
    """Print the typed line and, under Actions, the annotation, summary, and outputs."""
    line = outcome.report_line()
    print(line)
    if outcome.state is not EvidenceState.PASS:
        print(f"::warning title={outcome.validator}::{_escape_annotation(line)}")
    summary = f"- `{outcome.state.value}` {outcome.validator} `{outcome.reason or 'ok'}`\n"
    _append(os.environ.get("GITHUB_STEP_SUMMARY"), summary)
    _append(
        os.environ.get("GITHUB_OUTPUT"),
        f"state={outcome.state.value}\nreason={outcome.reason}\n",
    )


def _append(path: str | None, text: str) -> None:
    """Append ``text`` to a GitHub-provided file. A write failure is reported, not fatal."""
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as exc:
        print(f"::warning::could not write {Path(path).name}: {_escape_annotation(str(exc))}")


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--validator", required=True, help="stable name of the advisory check")
    parser.add_argument("--scope", required=True, help="what the check examines")
    parser.add_argument("--detail", default="", help="extra context for the report")
    parser.add_argument("--failure-state", choices=_FAILURE_STATES, default="BLOCKED")
    parser.add_argument("--failure-reason", default=REASON_SCRIPT_FAILED)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    step = modes.add_parser("step", help="report a swallowed step's recorded outcome")
    _common(step)
    step.add_argument("--outcome", required=True, help="${{ steps.<id>.outcome }}")
    run = modes.add_parser("run", help="run a command and report its exit code")
    _common(run)
    run.add_argument("--findings-exit", type=int, nargs="*", default=[1])
    run.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument(
        "--propagate-errors",
        action="store_true",
        help="exit non-zero when the command errors, not only when it finds something",
    )
    run.add_argument("command", nargs=argparse.REMAINDER, help="-- COMMAND [ARGS...]")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns 0 for a produced report, 2 for bad arguments.

    ``run --propagate-errors`` returns the command's own error code instead of 0.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if not _NAME_SHAPE.fullmatch(args.validator):
        parser.error(f"--validator {args.validator!r} must use letters, digits, '.', '_', '-'")
    if not _REASON_SHAPE.fullmatch(args.failure_reason):
        parser.error(f"--failure-reason {args.failure_reason!r} is not a dotted lowercase code")
    if args.mode == "run":
        if args.command[:1] == ["--"]:
            args.command = args.command[1:]
        if not args.command:
            parser.error("run needs a command after --")
        outcome, code = _run_command(args)
        _publish(outcome)
        return code if args.propagate_errors else EXIT_OK
    _publish(_outcome_from_step(args))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
