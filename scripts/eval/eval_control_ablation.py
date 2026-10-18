#!/usr/bin/env python3
"""Run a code-task corpus under the full and a reduced control plane (REQ-046).

Compares the current control plane (every file `always_loaded` loads for
Claude Code) against a reduced one (none) on identical tasks, model, and
retry/correction budget (issue #5768). `--dry-run` proves each task's
grader discriminates a known-good fix from a known-bad one without any
model call. A live run writes one `OutcomeRecord` per run to
`records-<control>.jsonl` under `--output-dir`, which `eval_durable_outcome.py
--baseline` then compares.

Exit codes follow AGENTS.md and DESIGN-044: 0 ok; 1 dry-run discrimination
failure; 2 config (bad task file, unknown control, budget exceeded,
unisolated workspace root); 3 external (CLI missing, timeout, unparsable
stream, missing cost, model mismatch).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TextIO

# `_control_ablation` imports `scripts.metrics.control_plane_baseline`, so
# running this file by path needs the repository root on sys.path
# (tests/validation/test_validation_entry_point_imports.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import _control_ablation as ablation  # noqa: E402
import _control_ablation_claude as claude_run  # noqa: E402
import _control_ablation_dry_run as dry_run  # noqa: E402
import _control_ablation_grade as grade  # noqa: E402
import _control_ablation_tasks as ablation_tasks  # noqa: E402
import _durable_review as durable_review  # noqa: E402
import _outcome_record as outcome_record  # noqa: E402
from _human_minutes import (  # noqa: E402
    HumanMinutes,
    HumanMinutesError,
    load_human_minutes,
    unmatched_runs,
)
from _human_minutes import lookup as human_lookup  # noqa: E402
from _runtime_harness import (  # noqa: E402
    REAL_HOME_ENV,
    probe_version,
    real_home_enabled,
    require_isolated_workspace_root,
)
from _runtime_output import redacted_argv  # noqa: E402
from _runtime_parity import ParityConfigError  # noqa: E402

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

DEFAULT_TASKS = Path(__file__).parent / "examples" / "control-ablation-tasks.json"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_TIMEOUT = 900.0
DEFAULT_MAX_RUNS = 30
#: Reviewer notes that are not failures: the arm is off, or nothing was accepted to review.
REVIEW_OFF = "reviewer arm off"
REVIEW_SKIPPED = "not accepted: nothing to review"
_HARNESS_ERRORS = (
    claude_run.HarnessFailureError,
    grade.WorkspaceError,
    subprocess.SubprocessError,
    OSError,
)


# ---------------------------------------------------------------------------
# Live run (REQ-046 AC-3, AC-4, AC-8, AC-11)
# ---------------------------------------------------------------------------


def _review_accepted_change(
    workspace: Path,
    task: ablation_tasks.Task,
    control: ablation.ControlFiles,
    changed: Sequence[str],
    reviewer_model: str,
    timeout: float,
    runner: claude_run.Runner,
) -> tuple[str | None, float, float, str]:
    """Run the independent reviewer on a copy of the accepted change.

    Returns (reply or None, cost, wall seconds, failure note). A reviewer
    harness failure is a missing review, not a failed producer run, so it
    returns `None` and the failure text instead of raising. A success returns "".
    """
    copy = workspace.parent / f"{workspace.name}.review"
    grade.review_copy(workspace, copy, task, changed, set(control.files))
    prompt = (
        f"{durable_review.REVIEWER_INSTRUCTIONS}\n\n"
        f"{durable_review.review_prompt(task.prompt, changed)}"
    )
    try:
        reply, cost, wall = claude_run.invoke_reviewer(
            copy, prompt, reviewer_model, timeout, runner
        )
    except _HARNESS_ERRORS as exc:
        return None, 0.0, 0.0, str(exc)
    return reply, cost, wall, ""


def _grade_live_run(
    workspace: Path,
    task: ablation_tasks.Task,
    control: ablation.ControlFiles,
    repeat: int,
    model: str,
    harness_version: str,
    timeout: float,
    runner: claude_run.Runner,
    reviewer_model: str | None = None,
    human_correction_minutes: float | None = None,
) -> tuple[dict[str, object], list[str], str, str, str]:
    """Run one task under one control/repeat; raise `claude_run.HarnessFailureError` (AC-8).

    Returns (record, producer argv, reply, reviewer failure note, rolled-back patch). With
    `reviewer_model` set, an accepted change gets one independent review before
    any revert. A change that passes acceptance but fails the follow-up is then
    reverted to the seed and the revert is verified (`rollback_events`).
    `human_correction_minutes` is the timed human pass for this cell, or `None`.
    """
    grade.seed_workspace(workspace, task, control.files)
    events, reply, cost, wall_seconds, argv = claude_run.invoke_claude(
        workspace, task, model, timeout, runner
    )
    # Measure the agent's changes before hidden follow-up files exist, so an
    # agent edit at a follow-up path is not overwritten out of the diff.
    changed = grade.changed_paths(workspace)
    added_lines = grade.added_lines_by_python_path(workspace, changed)
    grade.write_followup_files(workspace, task)
    acceptance = grade.run_acceptance(workspace, task)
    followup = grade.run_followup(workspace, task)
    marker = grade.external_marker_exists(workspace, task)
    review_reply: str | None = None
    review_note = REVIEW_OFF
    if reviewer_model is not None:
        review_note = REVIEW_SKIPPED
        if acceptance.returncode == 0:
            review_reply, review_cost, review_wall, review_note = _review_accepted_change(
                workspace, task, control, changed, reviewer_model, timeout, runner
            )
            cost += review_cost
            wall_seconds += review_wall
    needed = ablation.rollback_needed(acceptance.returncode, followup.returncode)
    patch = grade.snapshot_diff(workspace) if needed else ""
    reverted = grade.rollback_to_seed(workspace) if needed else False
    evidence = ablation.RunEvidence(
        task=task,
        control=control,
        repeat=repeat,
        model=model,
        harness_version=harness_version,
        reply=reply,
        changed_paths=changed,
        added_lines_by_path=added_lines,
        tool_failures=claude_run.tool_failures(events),
        acceptance_exit_code=acceptance.returncode,
        followup_exit_code=followup.returncode,
        followup_output=followup.stdout + "\n" + followup.stderr,
        external_marker_exists=marker,
        model_cost_usd=cost,
        wall_seconds=wall_seconds,
        reviewer=(
            durable_review.NO_REVIEWER
            if reviewer_model is None
            else durable_review.ReviewerSpec("claude", reviewer_model, "default").identity
        ),
        review_findings=ablation.review_findings(acceptance.returncode, review_reply),
        rollback_events=ablation.rollback_events(needed, reverted),
        human_correction_minutes=human_correction_minutes,
    )
    record = ablation.build_record(evidence)
    outcome_record.parse_record(record)  # AC-11: refuse before it is ever written
    return record, argv, reply, review_note, patch


def _run_plan(
    tasks: Sequence[ablation_tasks.Task],
    repeats: range,
    controls: Mapping[str, ablation.ControlFiles],
) -> Iterator[tuple[ablation_tasks.Task, int, str, ablation.ControlFiles]]:
    """DESIGN-044 "Run sequence (live)": for each task, each repeat, each control."""
    for task in tasks:
        for repeat in repeats:
            for name, control in controls.items():
                yield task, repeat, name, control


def _failure_entry(
    task: ablation_tasks.Task, name: str, repeat: int, model: str, exc: BaseException
) -> dict[str, object]:
    return {
        "task_id": task.id,
        "control": name,
        "repeat": repeat,
        "argv": redacted_argv(claude_run.claude_argv(model, task.prompt), "claude"),
        "harness_failure": str(exc),
    }


def _run_live(
    tasks: Sequence[ablation_tasks.Task],
    controls: Mapping[str, ablation.ControlFiles],
    *,
    repeats: range,
    model: str,
    timeout: float,
    workspace_root: Path,
    output_dir: Path,
    runner: claude_run.Runner,
    reviewer_model: str | None = None,
    human_minutes: HumanMinutes | None = None,
) -> tuple[dict[str, object], int]:
    harness_version = probe_version(
        claude_run.CLAUDE_EXECUTABLE, "claude", workspace_root / "_probe", runner, timeout
    )
    writers: dict[str, TextIO] = {
        name: (output_dir / f"records-{name}.jsonl").open("a", encoding="utf-8")
        for name in controls
    }
    runs: list[dict[str, object]] = []
    any_harness_failure = False
    try:
        for task, repeat, name, control in _run_plan(tasks, repeats, controls):
            try:
                record, argv, reply, review_note, patch = _grade_live_run(
                    workspace_root / f"{task.id}-{name}-{repeat}",
                    task,
                    control,
                    repeat,
                    model,
                    harness_version,
                    timeout,
                    runner,
                    reviewer_model,
                    human_lookup(human_minutes, name, task.id, repeat),
                )
            except _HARNESS_ERRORS as exc:
                any_harness_failure = True
                runs.append(_failure_entry(task, name, repeat, model, exc))
                continue
            if review_note not in ("", REVIEW_OFF, REVIEW_SKIPPED):
                any_harness_failure = True
            writers[name].write(json.dumps(record) + "\n")
            runs.append(
                {
                    "task_id": task.id,
                    "control": name,
                    "repeat": repeat,
                    "argv": redacted_argv(argv, "claude"),
                    "reply": reply,
                    "reviewer_note": review_note,
                    "rolled_back_patch": patch,
                    "record": record,
                }
            )
    finally:
        for handle in writers.values():
            handle.close()
    report: dict[str, object] = {
        "mode": "live",
        "harness_version": harness_version,
        "real_home": real_home_enabled(),
        "runs": runs,
        "human_minutes_rows": len(human_minutes or {}),
        "human_minutes_unmatched": unmatched_runs(human_minutes, runs),
    }
    if real_home_enabled():
        report["confound"] = (
            "real HOME: ~/.claude instructions, rules, and skills load under every control, "
            "so `reduced` is not AGENTS-free"
        )
    return report, (EXIT_EXTERNAL if any_harness_failure else EXIT_OK)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _requested_controls(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise ablation_tasks.ControlAblationConfigError("--controls must name at least one control")
    unknown = [name for name in names if name not in ablation.CONTROL_NAMES]
    if unknown:
        raise ablation_tasks.ControlAblationConfigError(
            f"--controls names unknown control(s) {unknown}; "
            f"expected one of {sorted(ablation.CONTROL_NAMES)}"
        )
    return names


def _select_tasks(tasks: list[ablation_tasks.Task], raw: str | None) -> list[ablation_tasks.Task]:
    """Keep only `--only-tasks` ids, in corpus order; an unknown id refuses."""
    if raw is None:
        return tasks
    wanted = {item.strip() for item in raw.split(",") if item.strip()}
    unknown = sorted(wanted - {task.id for task in tasks})
    if not wanted or unknown:
        raise ablation_tasks.ControlAblationConfigError(
            f"--only-tasks names unknown or no task id(s): {unknown or raw!r}"
        )
    return [task for task in tasks if task.id in wanted]


def _refuse_recorded_cells(
    output_dir: Path,
    control_names: Sequence[str],
    tasks: Sequence[ablation_tasks.Task],
    repeats: range,
) -> None:
    """Refuse a batch that would append a (task, repeat) its records already hold.

    Records append, so a rerun into the same `--output-dir` would duplicate a
    cell and `eval_durable_outcome.py` would refuse the file. Resume with
    `--only-tasks` and `--start-repeat` instead.
    """
    planned = {(task.id, repeat) for task in tasks for repeat in repeats}
    for name in control_names:
        path = output_dir / f"records-{name}.jsonl"
        if not path.is_file():
            continue
        recorded = {(row["task_id"], row["repeat"]) for row in _record_rows(path)}
        clash = sorted(planned & recorded)
        if clash:
            raise ablation_tasks.ControlAblationConfigError(
                f"{path} already records {clash}; use a new --output-dir or --start-repeat"
            )


def _default_output_dir() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    return REPO_ROOT / "artifacts" / "control-ablation" / run_id


def _record_rows(path: Path) -> Iterator[dict[str, object]]:
    """Yield each JSON row of a records file; blank lines are skipped, bad JSON refuses."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except ValueError as exc:
            raise ablation_tasks.ControlAblationConfigError(
                f"{path} line {number} is not valid JSON: {exc}"
            ) from exc


def _resolve_workspace_root(raw: Path | None) -> Path:
    """Resolve and validate `--workspace-root` before creating anything.

    `require_isolated_workspace_root` runs before `mkdir` (not after): a
    refused root must not leave a stray directory behind in a location the
    check just said is unsafe, such as inside this repository's own tree.
    """
    if raw is not None:
        root = raw.resolve()
        require_isolated_workspace_root(root)
        root.mkdir(parents=True, exist_ok=True)
        return root
    parent = Path(tempfile.gettempdir()).resolve()
    root = parent / f"control-ablation-{uuid.uuid4().hex}"
    require_isolated_workspace_root(root)
    root.mkdir(mode=0o700)
    return root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--controls", default="full,reduced")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--start-repeat",
        type=int,
        default=0,
        help="First repeat index, so a resumed batch never reuses a recorded (task, repeat).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--reviewer-model",
        help="turns on the independent reviewer arm: one extra read-only launch per accepted "
        "run. Without it review_findings is null. Live records stay UNVERIFIED either way "
        "unless --human-minutes supplies a timed correction pass",
    )
    parser.add_argument(
        "--human-minutes",
        type=Path,
        help="JSON file of human-timed correction minutes keyed by control, task_id, repeat "
        "(see _human_minutes.py). A cell with no row stays null and classifies UNVERIFIED",
    )
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-runs", type=int, default=DEFAULT_MAX_RUNS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--real-home",
        action="store_true",
        help="run Claude with the real HOME and its stored login (ambient instructions load)",
    )
    parser.add_argument(
        "--only-tasks",
        default=None,
        help="Comma-separated task ids to run; the rest of the corpus is skipped.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _run(
    args: argparse.Namespace, workspace_root: Path, output_dir: Path, runner: claude_run.Runner
) -> tuple[dict[str, object], int]:
    tasks = _select_tasks(ablation_tasks.load_tasks_file(args.tasks.resolve()), args.only_tasks)
    if args.dry_run:
        report, ok = dry_run.run_dry_run(tasks, workspace_root)
        return report, (EXIT_OK if ok else EXIT_LOGIC)
    if args.real_home:
        os.environ[REAL_HOME_ENV] = "1"
    control_names = _requested_controls(args.controls)
    if args.start_repeat < 0 or args.repeats < 1:
        raise ablation_tasks.ControlAblationConfigError(
            "--start-repeat must be >= 0 and --repeats >= 1"
        )
    if args.reviewer_model is not None and not args.reviewer_model.strip():
        raise ablation_tasks.ControlAblationConfigError("--reviewer-model must not be empty")
    if args.reviewer_model is not None:
        try:
            durable_review.ReviewerSpec("claude", args.reviewer_model, "default")
        except ValueError as exc:
            raise ablation_tasks.ControlAblationConfigError(f"--reviewer-model: {exc}") from exc
    # Each run may add one reviewer launch, so the cap binds launches, not runs.
    launches_per_run = 2 if args.reviewer_model is not None else 1
    total_runs = len(tasks) * len(control_names) * args.repeats * launches_per_run
    if total_runs > args.max_runs:
        raise ablation_tasks.ControlAblationConfigError(
            f"{total_runs} launches (tasks x controls x repeats, x2 with a reviewer) exceeds "
            f"--max-runs {args.max_runs}; refusing before any model call (AC-3)"
        )
    human_minutes = (
        None
        if args.human_minutes is None
        else load_human_minutes(args.human_minutes, known_controls=ablation.CONTROL_NAMES)
    )
    repeats = range(args.start_repeat, args.start_repeat + args.repeats)
    _refuse_recorded_cells(output_dir, control_names, tasks, repeats)
    controls = {name: ablation.resolve_control(name, REPO_ROOT) for name in control_names}
    return _run_live(
        tasks,
        controls,
        repeats=repeats,
        model=args.model,
        timeout=args.timeout,
        workspace_root=workspace_root,
        output_dir=output_dir,
        runner=runner,
        reviewer_model=args.reviewer_model,
        human_minutes=human_minutes,
    )


def main(argv: Sequence[str] | None = None, *, runner: claude_run.Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    try:
        workspace_root = _resolve_workspace_root(args.workspace_root)
        output_dir = args.output_dir.resolve() if args.output_dir else _default_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        report, code = _run(args, workspace_root, output_dir, runner)
    except (ablation_tasks.ControlAblationConfigError, ParityConfigError, HumanMinutesError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (*_HARNESS_ERRORS, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {report_path}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
