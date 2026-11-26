#!/usr/bin/env python3
"""Run the ship checks that have one right answer: tree, reviewed, pipeline.

Phase 2 and the discharge phase of the ship driver (ADR-127). Security scan
and tests stay with the model, because their findings need judgment.

Each requested check prints one ``CHECK: <name>=<state> [detail]`` line.
States: tree clean|dirty; reviewed PASS|FAIL|SKIPPED|ADVISORY;
pipeline PASS|FAIL|PENDING|DEFERRED.

Terminal line:
  any FAIL            -> STOP: check-failed, exit 1
  pipeline PENDING    -> NEXT: rerun-pipeline (the stored deadline carries over)
  pipeline DEFERRED   -> NEXT: publish-then-discharge (contributor: NEXT: report)
  all clear           -> NEXT: write-body (owner) or NEXT: report

Exit codes (ADR-035): 0 NEXT, 1 logic STOP, 2 config STOP, 3 external STOP,
4 auth STOP.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve(strict=True).parent  # the real entry, never a symlink's dir
if "_ship_common" not in sys.modules:  # pragma: no cover - fresh interpreter only
    _s = importlib.util.spec_from_file_location("_ship_common", _HERE / "_ship_common.py")
    _s.loader.exec_module(
        sys.modules.setdefault("_ship_common", importlib.util.module_from_spec(_s))
    )
common = sys.modules["_ship_common"]
detect_mod = common.load_sibling("ship_detect")

SCRIPT = "ship_preflight.py"
CHECKS = ("tree", "reviewed", "pipeline")
REASONS = detect_mod.REASONS | frozenset(
    {
        "check-failed",
        "validator-missing",
        "validator-config",
        "checks-query-failed",
        "pipeline-query-failed",
    }
)
TOTAL_WAIT_SECONDS = 1800
DEFAULT_CALL_WAIT = 480
MAX_CALL_WAIT = 540
POLL_SECONDS = 30
CHECKS_TIMEOUT_SECONDS = 300
AXIS_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_PASS_AXES_RE = re.compile(r"/review@([a-z0-9,-]+)")
# One Halt type across the ship scripts, so a detect-side halt reads as a halt here.
Halt = detect_mod.Halt


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.state in ("FAIL", "dirty")


def check_tree(root: Path) -> Check | Halt:
    done = common.git(["status", "--porcelain"], cwd=root)
    if done.returncode != 0:
        return Halt("no-repo", common.EXIT_CONFIG, "git status failed")
    entries = [line for line in done.stdout.splitlines() if line.strip()]
    if not entries:
        return Check("tree", "clean")
    return Check("tree", "dirty", f"files={len(entries)}")


def draft_exempt(ctx, draft: bool) -> bool:
    """Return whether ``--draft`` may skip the marker check.

    Only a new draft PR, or an open PR the host reports as a draft, is
    exempt. An existing non-draft PR, or one whose draft state is unknown,
    still needs the review marker, because a push there lands on a PR that
    can merge.
    """
    return draft and (ctx.pr is None or ctx.pr_draft is True)


def check_reviewed(ctx, draft: bool, require_axes: list[str]) -> Check | Halt:
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
    refused = f"draft exemption refused: PR {ctx.pr} is not a verified draft; " if draft else ""
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
        return Check("reviewed", "PASS", f"{refused}axes={axes}")
    if done.returncode == 1:
        lines = [line for line in done.stderr.splitlines() if line.strip()]
        return Check(
            "reviewed", "FAIL", refused + (lines[-1] if lines else "no valid review marker")
        )
    last = [line for line in done.stderr.splitlines() if line.strip()][-1:]
    detail = f"validator exit {done.returncode}" + (f": {last[0]}" if last else "")
    return Halt("validator-config", common.EXIT_CONFIG, detail)


def _github_head(ctx, pr: int) -> tuple[str, str] | Halt:
    done = common.run(
        ["gh", "pr", "view", str(pr), "--json", "headRefName,headRefOid"], cwd=ctx.root
    )
    if done.returncode != 0:
        return detect_mod.query_halt("checks-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict) or not data.get("headRefName") or not data.get("headRefOid"):
        return Halt("checks-query-failed", common.EXIT_EXTERNAL, f"PR {pr} head did not parse")
    return str(data["headRefName"]), str(data["headRefOid"])


def _binding(ctx, pr: int, branch: str, sha: str, after_publish: bool) -> Check | None:
    """Return a non-PASS check when PR ``pr`` does not carry this branch at HEAD."""
    if branch != ctx.branch:
        return Check("pipeline", "FAIL", f"pr={pr} head branch {branch} is not {ctx.branch}")
    if sha != ctx.head:
        detail = f"pr={pr} head {sha[:12]} is not HEAD {ctx.head[:12]}"
        if after_publish:
            return Check("pipeline", "PENDING", detail + "; host has not seen the push yet")
        return Check("pipeline", "DEFERRED", detail + "; checks run after publish")
    return None


def _read_github_checks(ctx, pr: int, wait_seconds: int) -> tuple[int, dict] | Check | Halt:
    """Run get_pr_checks.py once; return (exit code, Data), a PENDING check, or a Halt.

    It waits at most ``min(wait_seconds, CHECKS_TIMEOUT_SECONDS)``. Zero reads once.
    """
    budget = max(0, min(wait_seconds, CHECKS_TIMEOUT_SECONDS))
    helper = common.skill_script("github", "pr", "get_pr_checks.py")
    if not helper.is_file():
        return Halt("checks-query-failed", common.EXIT_CONFIG, "get_pr_checks.py not found")
    argv = [
        sys.executable,
        "-I",
        str(helper),
        "--pull-request",
        str(pr),
        *(["--wait", "--timeout-seconds", str(budget)] if budget else []),
        "--required-only",
        "--output-format",
        "json",
    ]
    done = common.run(argv, cwd=ctx.root, timeout=budget + 60)
    if done.returncode == 4:
        return Halt("auth-failed", common.EXIT_AUTH, "check query was not authorized")
    lines = done.stdout.strip().splitlines()
    envelope = common.parse_json(lines[-1]) if lines else None
    data = envelope.get("Data") if isinstance(envelope, dict) else None
    if done.returncode == 7:
        # Exit 7 is a timeout or an incomplete rollup, and it can still carry a
        # failed required check, so the Data decides when it parses.
        if isinstance(data, dict):
            return 7, data
        return Check("pipeline", "PENDING", f"pr={pr} required checks still running")
    if not isinstance(data, dict) or done.returncode not in (0, 1):
        error = envelope.get("Error") if isinstance(envelope, dict) else None
        message = error.get("Message") if isinstance(error, dict) else None
        stderr = [line for line in done.stderr.splitlines() if line.strip()][-1:]
        reason = message or (stderr[0] if stderr else "")
        detail = f"get_pr_checks exit {done.returncode}" + (f": {reason}" if reason else "")
        return Halt("checks-query-failed", common.EXIT_EXTERNAL, detail)
    return done.returncode, data


def _github_verdict(ctx, pr: int, code: int, data: dict) -> Check:
    """Turn one get_pr_checks.py result into PASS or FAIL. Exit 0 alone is not green."""
    if code == 0 and data.get("RequiredState") == "SUCCESS" and data.get("AllPassing") is True:
        return Check("pipeline", "PASS", f"pr={pr} head={ctx.head[:12]}")
    still_running = code == 7 or data.get("RequiredState") == "PENDING"
    if still_running and not data.get("FailedRequiredChecks"):
        # Read without waiting, or the wait ended early: still running, not failed.
        pending = _check_names(data, ("PendingRequiredChecks",))
        tail = " pending=" + ",".join(pending) if pending else ""
        return Check("pipeline", "PENDING", f"pr={pr} required checks still running{tail}")
    names = _check_names(
        data, ("FailedRequiredChecks", "MissingRequiredChecks", "PendingRequiredChecks")
    )
    detail = f"pr={pr} required={data.get('RequiredState')} all_passing={data.get('AllPassing')}"
    if names:
        detail += " failing=" + ",".join(names)
    return Check("pipeline", "FAIL", detail)


def _check_names(data: dict, keys: tuple[str, ...]) -> list[str]:
    """Return up to 10 check names from the listed Data keys."""
    names = []
    for key in keys:
        for item in data.get(key) or []:
            names.append(str(item.get("Name", item)) if isinstance(item, dict) else str(item))
    return names[:10]


def _github_pipeline(ctx, pr: int, after_publish: bool, wait_seconds: int) -> Check | Halt:
    """Read CI only for PR ``pr`` at this branch and HEAD, and re-check the head after."""
    before = _github_head(ctx, pr)
    if isinstance(before, Halt):
        return before
    mismatch = _binding(ctx, pr, *before, after_publish)
    if mismatch is not None:
        return mismatch
    read = _read_github_checks(ctx, pr, wait_seconds)
    if not isinstance(read, tuple):
        return read
    after = _github_head(ctx, pr)
    if isinstance(after, Halt):
        return after
    if after != before:
        return Check("pipeline", "PENDING", f"pr={pr} head moved during the check")
    return _github_verdict(ctx, pr, *read)


def _ado_policy_rows(ctx, pr: int) -> list[dict] | Halt:
    done = common.run(
        [
            "az",
            "repos",
            "pr",
            "policy",
            "list",
            "--id",
            str(pr),
            "--query",
            "[?configuration.isBlocking && configuration.isEnabled && "
            "configuration.type.displayName=='Build'].{status: status, buildId: context.buildId}",
            "--output",
            "json",
        ],
        cwd=ctx.root,
    )
    if done.returncode != 0:
        return detect_mod.query_halt("pipeline-query-failed", done)
    rows = common.parse_json(done.stdout)
    if not isinstance(rows, list):
        return Halt("pipeline-query-failed", common.EXIT_EXTERNAL, "policy list did not parse")
    return [
        row
        for row in rows
        if isinstance(row, dict) and row.get("status") not in (None, "", "notApplicable")
    ]


def _ado_state(ctx, pr: int) -> dict | Halt:
    done = common.run(
        [
            "az",
            "repos",
            "pr",
            "show",
            "--id",
            str(pr),
            "--query",
            "{source: sourceRefName, head: lastMergeSourceCommit.commitId, "
            "merge: lastMergeCommit.commitId}",
            "--output",
            "json",
        ],
        cwd=ctx.root,
    )
    if done.returncode != 0:
        return detect_mod.query_halt("pipeline-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict):
        return Halt("pipeline-query-failed", common.EXIT_EXTERNAL, "pr show did not parse")
    return data


def _ado_evaluate(ctx, pr: int, rows: list[dict], state: dict) -> Check | Halt:
    merge_commit = str(state.get("merge") or "")
    if not merge_commit:
        return Check("pipeline", "FAIL", f"pr={pr} has no merge commit to compare builds against")
    failures = []
    for row in rows:
        status = str(row.get("status"))
        build_id = row.get("buildId")
        if status != "approved" or build_id in (None, "", "None"):
            failures.append(f"policy={status} build={build_id}")
            continue
        build = common.run(
            [
                "az",
                "pipelines",
                "build",
                "show",
                "--id",
                str(build_id),
                "--query",
                "{result: result, sourceVersion: sourceVersion}",
                "--output",
                "json",
            ],
            cwd=ctx.root,
        )
        if build.returncode != 0:
            return detect_mod.query_halt("pipeline-query-failed", build)
        info = common.parse_json(build.stdout)
        if not isinstance(info, dict):
            return Halt("pipeline-query-failed", common.EXIT_EXTERNAL, "build show did not parse")
        if info.get("result") != "succeeded" or info.get("sourceVersion") != merge_commit:
            failures.append(
                f"build={build_id} result={info.get('result')} at={info.get('sourceVersion')}"
            )
    if failures:
        return Check(
            "pipeline", "FAIL", f"pr={pr} merge={merge_commit} " + "; ".join(failures[:10])
        )
    return Check("pipeline", "PASS", f"pr={pr} builds={len(rows)} merge={merge_commit}")


def _ado_moved(ctx, pr: int, state: dict) -> Check | Halt | None:
    """Re-read the PR after a check; PENDING when its head or merge commit moved."""
    again = _ado_state(ctx, pr)
    if isinstance(again, Halt):
        return again
    if again.get("head") != state.get("head"):
        return Check("pipeline", "PENDING", f"pr={pr} head moved during the check")
    if again.get("merge") != state.get("merge"):
        # The builds ran against a newer merge commit: check them again.
        return Check("pipeline", "PENDING", f"pr={pr} merge commit moved during the check")
    return None


def _ado_pipeline(ctx, pr: int, wait_seconds: int, after_publish: bool) -> Check | Halt:
    state = _ado_state(ctx, pr)
    if isinstance(state, Halt):
        return state
    source = str(state.get("source") or "")
    branch = source[len("refs/heads/") :] if source.startswith("refs/heads/") else source
    mismatch = _binding(ctx, pr, branch, str(state.get("head") or ""), after_publish)
    if mismatch is not None:
        return mismatch
    # Leave room for the evaluation calls after the wait, inside the run budget.
    call_end = time.monotonic() + min(wait_seconds, max(0.0, common.remaining_seconds() - 120))
    while True:
        rows = _ado_policy_rows(ctx, pr)
        if isinstance(rows, Halt):
            return rows
        pending = [row for row in rows if row.get("status") in ("queued", "running")]
        if rows and not pending:
            verdict = _ado_evaluate(ctx, pr, rows, state)
            return _ado_moved(ctx, pr, state) or verdict
        if not rows and not after_publish:
            return Check("pipeline", "FAIL", f"pr={pr} has no blocking build policy evaluation")
        remaining = call_end - time.monotonic()
        if remaining <= 0:
            return Check(
                "pipeline", "PENDING", f"pr={pr} {len(pending)} of {len(rows)} queued or running"
            )
        time.sleep(min(POLL_SECONDS, remaining))


def check_pipeline(ctx, pr: int | None, wait_seconds: int, after_publish: bool) -> Check | Halt:
    if pr is None:
        return Check("pipeline", "DEFERRED", "no open PR yet")
    if ctx.host == "github":
        return _github_pipeline(ctx, pr, after_publish, wait_seconds)
    return _ado_pipeline(ctx, pr, wait_seconds, after_publish)


def build_parser():
    parser = common.ResultParser(prog=SCRIPT, description="Run the fixed ship checks.")
    parser.add_argument("--check", action="append", choices=CHECKS, required=True)
    parser.add_argument("--base", default=None)
    parser.add_argument(
        "--pr", type=int, default=None, help="PR to check; marks the discharge phase"
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Skip the marker check for a new draft PR or a host-reported draft PR only",
    )
    parser.add_argument("--require-axis", action="append", default=[])
    parser.add_argument(
        "--deadline", type=int, default=None, help="Epoch second printed by a PENDING run"
    )
    parser.add_argument("--wait-seconds", type=int, default=DEFAULT_CALL_WAIT)
    common.add_output_format_arg(parser)
    return parser


def _validate(args) -> str | None:
    if args.base is not None and not common.safe_ref(args.base):
        return "--base is not a plain ref"
    if args.pr is not None and args.pr <= 0:
        return "--pr must be a positive integer"
    if args.deadline is not None and args.deadline > int(time.time()) + TOTAL_WAIT_SECONDS:
        return "--deadline must be the PIPELINE_DEADLINE value a PENDING run printed"
    if not 0 <= args.wait_seconds <= MAX_CALL_WAIT:
        return f"--wait-seconds must be 0 to {MAX_CALL_WAIT}"
    for axis in args.require_axis:
        if not AXIS_RE.match(axis):
            return "--require-axis must be a lowercase axis name"
    if len(set(args.check)) != len(args.check):
        return "--check repeats a check"
    return None


def bound_deadline(ctx, pr: int | None, requested: int | None, *, store: bool = False) -> int:
    """The 30-minute pipeline deadline for this PR and HEAD.

    The window starts when a pipeline check first returns PENDING, which
    stores it in a scratch state file keyed by host, PR, and HEAD. Later calls
    read that file, so a rerun or an omitted --deadline cannot extend it. A
    call that only reads (``store`` false) never starts the window. A
    --deadline can only shorten it.
    """
    window = int(time.time()) + TOTAL_WAIT_SECONDS
    stored = window
    if pr is not None:
        name = f"ship-deadline-{ctx.host}-{pr}-{ctx.head[:12]}.txt"
        stored = common.stored_int(ctx.root, name, window, store=store)
    return min(stored, requested) if requested is not None else stored


def _run_check(name, ctx, args, pr, wait_seconds, after_publish, deadline) -> Check | Halt:
    """Run one named check. A pipeline still pending past the deadline is a FAIL."""
    if name == "tree":
        return check_tree(ctx.root)
    if name == "reviewed":
        return check_reviewed(ctx, args.draft, args.require_axis)
    outcome = check_pipeline(ctx, pr, wait_seconds, after_publish)
    if isinstance(outcome, Check) and outcome.state == "PENDING" and time.time() >= deadline:
        return Check("pipeline", "FAIL", f"still pending after {TOTAL_WAIT_SECONDS // 60} minutes")
    return outcome


def _terminal(result, checks: list[Check], deadline: int, ends_on_report: bool, contributor: bool):
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


def run(argv: list[str]):
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
        deadline = bound_deadline(ctx, pr, args.deadline, store=True)
    contributor = ctx.mode == "contributor"
    return (
        _terminal(result, checks, deadline, after_publish or contributor, contributor),
        fmt,
        ctx.root,
    )


def main(argv: list[str] | None = None) -> int:
    result, fmt, root = run(sys.argv[1:] if argv is None else argv)
    return common.emit(result, fmt, root)


if (
    __name__ == "__main__"
):  # pragma: no cover - runs only in a fresh interpreter; see test_ship_edges.py::test_script_runs_under_isolated_mode
    raise SystemExit(main())
