#!/usr/bin/env python3
"""Run the ship checks that have one right answer: tree, reviewed, pipeline.

Phase 2 and the discharge phase of the ship driver (ADR-127). Security scan
and tests stay with the model, because their findings need judgment.

Each requested check prints one ``CHECK: <name>=<state> [detail]`` line.
States: tree clean|dirty; reviewed PASS|FAIL|SKIPPED|ADVISORY;
pipeline PASS|FAIL|PENDING|DEFERRED.

Terminal line:
  any FAIL            -> STOP: check-failed, exit 1
  pipeline PENDING    -> NEXT: rerun-pipeline (pass the printed --deadline)
  pipeline DEFERRED   -> NEXT: publish-then-discharge
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


def _load(name: str):
    path = Path(__file__).resolve().with_name(f"{name}.py")
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = _load("_ship_common")
detect_mod = _load("ship_detect")

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
_AXIS_RE = re.compile(r"^[a-z][a-z0-9-]*$")
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


def check_reviewed(ctx, draft: bool, require_axes: list[str]) -> Check | Halt:
    if draft:
        return Check("reviewed", "SKIPPED", "draft")
    if ctx.mode == "contributor":
        return Check("reviewed", "ADVISORY", "contributor mode: attest the review in the report")
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
        return Check("reviewed", "PASS", f"axes={axes}")
    if done.returncode == 1:
        lines = [line for line in done.stderr.splitlines() if line.strip()]
        return Check("reviewed", "FAIL", lines[-1] if lines else "no valid review marker")
    return Halt("validator-config", common.EXIT_CONFIG, f"validator exit {done.returncode}")


def _github_pipeline(ctx, pr: int) -> Check | Halt:
    helper = common.skill_script("github", "pr", "get_pr_checks.py")
    if not helper.is_file():
        return Halt("checks-query-failed", common.EXIT_CONFIG, "get_pr_checks.py not found")
    argv = [
        sys.executable,
        "-I",
        str(helper),
        "--pull-request",
        str(pr),
        "--wait",
        "--required-only",
        "--timeout-seconds",
        str(CHECKS_TIMEOUT_SECONDS),
        "--output-format",
        "json",
    ]
    done = common.run(argv, cwd=ctx.root, timeout=CHECKS_TIMEOUT_SECONDS + 60)
    if done.returncode == 7:
        return Check("pipeline", "PENDING", "required checks still running")
    if done.returncode == 4:
        return Halt("auth-failed", common.EXIT_AUTH, "check query was not authorized")
    lines = done.stdout.strip().splitlines()
    envelope = common.parse_json(lines[-1]) if lines else None
    data = envelope.get("Data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict) or done.returncode not in (0, 1):
        return Halt(
            "checks-query-failed", common.EXIT_EXTERNAL, f"get_pr_checks exit {done.returncode}"
        )
    if (
        done.returncode == 0
        and data.get("RequiredState") == "SUCCESS"
        and data.get("AllPassing") is True
    ):
        return Check("pipeline", "PASS", f"pr={pr}")
    names = []
    for key in ("FailedRequiredChecks", "MissingRequiredChecks", "PendingRequiredChecks"):
        for item in data.get(key) or []:
            names.append(str(item.get("Name", item)) if isinstance(item, dict) else str(item))
    detail = f"pr={pr} required={data.get('RequiredState')} all_passing={data.get('AllPassing')}"
    if names:
        detail += " failing=" + ",".join(names[:10])
    return Check("pipeline", "FAIL", detail)


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
        return detect_mod._query_halt("pipeline-query-failed", done)
    rows = common.parse_json(done.stdout)
    if not isinstance(rows, list):
        return Halt("pipeline-query-failed", common.EXIT_EXTERNAL, "policy list did not parse")
    return [
        row
        for row in rows
        if isinstance(row, dict) and row.get("status") not in (None, "", "notApplicable")
    ]


def _ado_evaluate(ctx, pr: int, rows: list[dict]) -> Check | Halt:
    done = common.run(
        [
            "az",
            "repos",
            "pr",
            "show",
            "--id",
            str(pr),
            "--query",
            "lastMergeCommit.commitId",
            "--output",
            "tsv",
        ],
        cwd=ctx.root,
    )
    if done.returncode != 0:
        return detect_mod._query_halt("pipeline-query-failed", done)
    merge_commit = done.stdout.strip()
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
            return detect_mod._query_halt("pipeline-query-failed", build)
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


def _ado_pipeline(ctx, pr: int, wait_seconds: int, after_publish: bool) -> Check | Halt:
    call_end = time.monotonic() + wait_seconds
    while True:
        rows = _ado_policy_rows(ctx, pr)
        if isinstance(rows, Halt):
            return rows
        pending = [row for row in rows if row.get("status") in ("queued", "running")]
        if rows and not pending:
            return _ado_evaluate(ctx, pr, rows)
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
        return _github_pipeline(ctx, pr)
    return _ado_pipeline(ctx, pr, wait_seconds, after_publish)


def build_parser():
    parser = common.ResultParser(prog=SCRIPT, description="Run the fixed ship checks.")
    parser.add_argument("--check", action="append", choices=CHECKS, required=True)
    parser.add_argument("--base", default=None)
    parser.add_argument(
        "--pr", type=int, default=None, help="PR to check; marks the discharge phase"
    )
    parser.add_argument("--draft", action="store_true", help="Skip the review marker check")
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
    if not 0 <= args.wait_seconds <= MAX_CALL_WAIT:
        return f"--wait-seconds must be 0 to {MAX_CALL_WAIT}"
    for axis in args.require_axis:
        if not _AXIS_RE.match(axis):
            return "--require-axis must be a lowercase axis name"
    if len(set(args.check)) != len(args.check):
        return "--check repeats a check"
    return None


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
    deadline = args.deadline if args.deadline is not None else int(time.time()) + TOTAL_WAIT_SECONDS
    wait_seconds = max(0, min(args.wait_seconds, deadline - int(time.time())))

    checks: list[Check] = []
    for name in args.check:
        if name == "tree":
            outcome = check_tree(ctx.root)
        elif name == "reviewed":
            outcome = check_reviewed(ctx, args.draft, args.require_axis)
        else:
            outcome = check_pipeline(ctx, pr, wait_seconds, after_publish)
            if (
                isinstance(outcome, Check)
                and outcome.state == "PENDING"
                and time.time() >= deadline
            ):
                outcome = Check(
                    "pipeline", "FAIL", f"still pending after {TOTAL_WAIT_SECONDS // 60} minutes"
                )
        if isinstance(outcome, Halt):
            return result.stop(outcome.reason, outcome.code, outcome.detail), fmt, ctx.root
        checks.append(outcome)
        result.add("CHECK", f"{outcome.name}={outcome.state} {outcome.detail}".rstrip())

    failed = [check.name for check in checks if check.failed]
    states = {check.name: check.state for check in checks}
    if failed:
        return result.stop("check-failed", common.EXIT_LOGIC, ",".join(failed)), fmt, ctx.root
    if states.get("pipeline") == "PENDING":
        result.add("PIPELINE_DEADLINE", deadline)
        return result.next("rerun-pipeline"), fmt, ctx.root
    if states.get("pipeline") == "DEFERRED":
        return result.next("publish-then-discharge"), fmt, ctx.root
    if after_publish or ctx.mode == "contributor":
        return result.next("report"), fmt, ctx.root
    return result.next("write-body"), fmt, ctx.root


def main(argv: list[str] | None = None) -> int:
    result, fmt, root = run(sys.argv[1:] if argv is None else argv)
    return common.emit(result, fmt, root)


if __name__ == "__main__":
    raise SystemExit(main())
