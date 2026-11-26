#!/usr/bin/env python3
"""Run the ship checks that have one right answer: tree, reviewed, pipeline.

Phase 2 and the discharge phase of the ship driver (ADR-127). Security scan
and tests stay with the model, because their findings need judgment.

Each requested check prints one ``CHECK: <name>=<state> [detail]`` line.
States: tree clean|dirty; reviewed PASS|FAIL|SKIPPED|ADVISORY;
pipeline PASS|FAIL|PENDING|DEFERRED.

Terminal line:
  any FAIL or tree=dirty -> STOP: check-failed, exit 1
  pipeline PENDING    -> NEXT: rerun-pipeline (the stored deadline carries over)
  pipeline DEFERRED   -> NEXT: publish-then-discharge (contributor: NEXT: report)
  all clear           -> NEXT: write-body (owner) or NEXT: report

Exit codes (ADR-035): 0 NEXT, 1 logic STOP, 2 config STOP, 3 external STOP,
4 auth STOP.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    import _ship_common as common
    import _ship_pipeline as pipeline_mod
    import ship_detect as detect_mod
    from _ship_pipeline import Check, check_pipeline
    from ship_detect import Context, Halt
else:
    _HERE = Path(__file__).resolve(strict=True).parent  # the real entry, never a symlink's dir
    if "_ship_common" not in sys.modules:  # pragma: no cover - fresh interpreter only
        _s = importlib.util.spec_from_file_location("_ship_common", _HERE / "_ship_common.py")
        _s.loader.exec_module(
            sys.modules.setdefault("_ship_common", importlib.util.module_from_spec(_s))
        )
    common = sys.modules["_ship_common"]
    detect_mod = common.load_sibling("ship_detect")
    pipeline_mod = common.load_sibling("_ship_pipeline")
    # One Halt type across the ship scripts, so a detect-side halt reads as a halt here.
    Halt = detect_mod.Halt
    Check = pipeline_mod.Check
    check_pipeline = pipeline_mod.check_pipeline

SCRIPT = "ship_preflight.py"
CHECKS = ("tree", "reviewed", "pipeline")
REASONS = detect_mod.REASONS | frozenset(
    {
        "check-failed",
        "validator-missing",
        "validator-config",
        "checks-query-failed",
        "pipeline-query-failed",
        "deadline-unstored",
    }
)
TOTAL_WAIT_SECONDS = 1800
DEFAULT_CALL_WAIT = 480
MAX_CALL_WAIT = 540
AXIS_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_PASS_AXES_RE = re.compile(r"/review@([a-z0-9,-]+)")


def check_tree(root: Path) -> Check | Halt:
    """Clean or dirty, ignoring the scratch directory the ship scripts write to."""
    scratch = f":(exclude){common.SCRATCH_REL.as_posix()}"
    done = common.git(["status", "--porcelain", "--", ".", scratch], cwd=root)
    if done.returncode != 0:
        cause = common.cause_line(done.stderr, "git status failed")
        code = common.EXIT_EXTERNAL if done.returncode in (124, 126, 127) else common.EXIT_CONFIG
        return Halt("no-repo", code, cause)
    entries = [line for line in done.stdout.splitlines() if line.strip()]
    if not entries:
        return Check("tree", "clean")
    return Check("tree", "dirty", f"files={len(entries)}")


def draft_exempt(ctx: Context, draft: bool) -> bool:
    """Return whether ``--draft`` may skip the marker check.

    Only a new draft PR, or an open PR the host reports as a draft, is
    exempt. An existing non-draft PR, or one whose draft state is unknown,
    still needs the review marker, because a push there lands on a PR that
    can merge.
    """
    return draft and (ctx.pr is None or ctx.pr_draft is True)


def check_reviewed(ctx: Context, draft: bool, require_axes: list[str]) -> Check | Halt:
    exempt = draft_exempt(ctx, draft)
    if require_axes and (exempt or ctx.mode == "contributor"):
        return Check(
            "reviewed",
            "FAIL",
            "required axes cannot be verified without a review marker: " + ",".join(require_axes),
        )
    if exempt:
        return Check("reviewed", "SKIPPED", "draft")
    if ctx.mode == "contributor":
        return Check("reviewed", "ADVISORY", "contributor mode: attest the review in the report")
    refused = f"draft exemption refused: PR {ctx.pr} is not a verified draft" if draft else ""
    validator = common.skill_script("review", "validate_review_marker.py")
    if not validator.is_file():
        return Halt("validator-missing", common.EXIT_CONFIG, "review skill validator not found")
    argv = [sys.executable, "-I", str(validator), "--ref", "HEAD", "--repo-root", str(ctx.root)]
    for axis in require_axes:
        argv.extend(["--require-axis", axis])
    done = common.run(argv, cwd=ctx.root)
    if done.returncode == 0:
        match = _PASS_AXES_RE.search(done.stdout)
        axes = match.group(1) if match else "unknown"
        # The spec shape is ``axes=<list>``, so a refusal note follows it.
        return Check("reviewed", "PASS", f"axes={axes}" + (f"; {refused}" if refused else ""))
    if done.returncode == 1:
        lines = [line for line in done.stderr.splitlines() if line.strip()]
        cause = lines[-1] if lines else "no valid review marker"
        return Check("reviewed", "FAIL", f"{refused}; {cause}" if refused else cause)
    last = [line for line in done.stderr.splitlines() if line.strip()][-1:]
    detail = f"validator exit {done.returncode}" + (f": {last[0]}" if last else "")
    return Halt("validator-config", common.EXIT_CONFIG, detail)


def build_parser() -> common.ResultParser:
    parser = common.ResultParser(prog=SCRIPT, description="Run the fixed ship checks.")
    parser.add_argument("--check", action="append", choices=CHECKS, required=True)
    parser.add_argument("--base", default=None)
    parser.add_argument("--pr", type=int, default=None, help="PR to check (discharge phase)")
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Skip the marker check for a new draft PR or a host-reported draft PR only",
    )
    parser.add_argument("--require-axis", action="append", default=[])
    parser.add_argument("--deadline", type=int, default=None, help="PENDING run's epoch second")
    parser.add_argument("--wait-seconds", type=int, default=DEFAULT_CALL_WAIT)
    common.add_output_format_arg(parser)
    return parser


def _validate(args: argparse.Namespace) -> str | None:
    if args.base is not None and not detect_mod.base_arg_ok(args.base):
        return "--base is not a plain ref"
    if args.pr is not None and args.pr <= 0:
        return "--pr must be a positive integer"
    if args.deadline is not None and args.deadline > int(time.time()) + TOTAL_WAIT_SECONDS:
        return "--deadline must be the PIPELINE_DEADLINE value a PENDING run printed"
    if not 0 <= args.wait_seconds <= MAX_CALL_WAIT:
        return f"--wait-seconds must be 0 to {MAX_CALL_WAIT}"
    for axis in args.require_axis:
        if not AXIS_RE.fullmatch(axis):
            return "--require-axis must be a lowercase axis name"
    if len(set(args.check)) != len(args.check):
        return "--check repeats a check"
    return None


@overload
def bound_deadline(
    ctx: Context, pr: int | None, requested: int | None, *, store: Literal[False] = False
) -> int:
    """Read the deadline; a read-only call always yields one."""


@overload
def bound_deadline(
    ctx: Context, pr: int | None, requested: int | None, *, store: Literal[True]
) -> int | None:
    """Store the deadline; None when it could not be stored."""


def bound_deadline(
    ctx: Context, pr: int | None, requested: int | None, *, store: bool = False
) -> int | None:
    """The 30-minute pipeline deadline for this PR and HEAD.

    The window starts when a pipeline check first returns PENDING, which
    stores it in a scratch state file keyed by host, PR, and HEAD. Later calls
    read that file, so a rerun or an omitted --deadline cannot extend it. A
    call that only reads (``store`` false) never starts the window. A
    --deadline can only shorten it. None means the window could not be
    stored, so a rerun could extend it.
    """
    window = int(time.time()) + TOTAL_WAIT_SECONDS
    stored: int | None = window
    if pr is not None:
        name = f"ship-deadline-{ctx.host}-{pr}-{ctx.head[:12]}.txt"
        stored = common.stored_int(ctx.root, name, window, store=store)
    if stored is None or requested is None:
        return stored
    return min(stored, requested)


def _run_check(
    name: str,
    ctx: Context,
    args: argparse.Namespace,
    pr: int | None,
    wait_seconds: int,
    after_publish: bool,
    deadline: int,
) -> Check | Halt:
    """Run one named check. A pipeline still pending past the deadline is a FAIL."""
    if name == "tree":
        return check_tree(ctx.root)
    if name == "reviewed":
        return check_reviewed(ctx, args.draft, args.require_axis)
    outcome = check_pipeline(ctx, pr, wait_seconds, after_publish)
    if isinstance(outcome, Check) and outcome.state == "PENDING" and time.time() >= deadline:
        waited = f"{TOTAL_WAIT_SECONDS // 60} minutes"
        return Check("pipeline", "FAIL", f"still pending after {waited}: {outcome.detail}")
    return outcome


def _terminal(
    result: common.Result,
    checks: list[Check],
    deadline: int,
    ends_on_report: bool,
    contributor: bool,
) -> common.Result:
    """Set the terminal line from the check states."""
    failed = [check.name for check in checks if check.failed]
    states = {check.name: check.state for check in checks}
    if failed:
        return result.stop("check-failed", common.EXIT_LOGIC, ",".join(failed))
    if states.get("pipeline") == "PENDING":
        result.add("PIPELINE_DEADLINE", deadline)
        return result.next("rerun-pipeline")
    if states.get("pipeline") == "DEFERRED":
        # A contributor never publishes, so a deferred pipeline only reports.
        return result.next("report" if contributor else "publish-then-discharge")
    return result.next("report" if ends_on_report else "write-body")


def run(argv: list[str]) -> tuple[common.Result, str, Path | None]:
    result = common.Result(SCRIPT, REASONS)
    try:
        args = build_parser().parse_args(argv)
    except common.UsageError as exc:
        return result.stop("bad-arguments", common.EXIT_CONFIG, exc), common.peek_format(argv), None
    fmt = common.resolve_format(args.output_format)
    problem = _validate(args)
    if problem:
        return result.stop("bad-arguments", common.EXIT_CONFIG, problem), fmt, None
    ctx = detect_mod.detect(base=args.base)
    if isinstance(ctx, detect_mod.Halt):
        return result.stop(ctx.reason, ctx.code, ctx.detail), fmt, common.repo_root()
    detect_mod.add_context_lines(result, ctx)
    pr = args.pr if args.pr is not None else ctx.pr
    after_publish = args.pr is not None
    deadline = bound_deadline(ctx, pr, args.deadline)
    wait_seconds = max(0, min(args.wait_seconds, deadline - int(time.time())))

    checks: list[Check] = []
    for name in args.check:
        outcome = _run_check(name, ctx, args, pr, wait_seconds, after_publish, deadline)
        if isinstance(outcome, Halt):
            return result.stop(outcome.reason, outcome.code, outcome.detail), fmt, ctx.root
        checks.append(outcome)
        result.add("CHECK", f"{outcome.name}={outcome.state} {outcome.detail}".rstrip())
    if any(check.name == "pipeline" and check.state == "PENDING" for check in checks):
        stored = bound_deadline(ctx, pr, args.deadline, store=True)
        if stored is None:
            detail = f"cannot store the pipeline deadline under {common.SCRATCH_REL.as_posix()}"
            return result.stop("deadline-unstored", common.EXIT_CONFIG, detail), fmt, ctx.root
        deadline = stored
    contributor = ctx.mode == "contributor"
    ends_on_report = after_publish or contributor
    return _terminal(result, checks, deadline, ends_on_report, contributor), fmt, ctx.root


def main(argv: list[str] | None = None) -> int:
    result, fmt, root = run(sys.argv[1:] if argv is None else argv)
    return common.emit(result, fmt, root)


# Runs only in a fresh interpreter; see test_ship_edges.py::test_script_runs_under_isolated_mode
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
