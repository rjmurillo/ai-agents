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
import json
import os
import subprocess
import sys
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
import _control_ablation_batch as batch  # noqa: E402
import _control_ablation_claude as claude_run  # noqa: E402
import _control_ablation_dry_run as dry_run  # noqa: E402
import _control_ablation_grade as grade  # noqa: E402
import _control_ablation_history as history  # noqa: E402
import _control_ablation_tasks as ablation_tasks  # noqa: E402
import _durable_review as durable_review  # noqa: E402
import _outcome_record as outcome_record  # noqa: E402
from _run_changes import path_safe, write_patch  # noqa: E402
from _runtime_harness import (  # noqa: E402
    REAL_HOME_ENV,
    probe_version,
    real_home_enabled,
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


# Live run (REQ-046 AC-3, AC-4, AC-8, AC-11)


def _prepare_review_copy(
    workspace: Path,
    task: ablation_tasks.Task,
    control: ablation.ControlFiles,
    changed: Sequence[str],
) -> tuple[Path | None, str]:
    """Copy the agent's change for the reviewer, before `write_followup_files`.

    A hidden follow-up file written first would overwrite an agent edit at the
    same path. Returns (copy, ""), or (None, failure note): a copy that cannot
    be built is a missing review, not a lost producer run.
    """
    copy = workspace.parent / f"{workspace.name}.review"
    try:
        grade.review_copy(workspace, copy, task, changed, set(control.files))
    except (ablation_tasks.ControlAblationConfigError, OSError) as exc:
        return None, f"review copy failed: {exc}"
    return copy, ""


def _review_accepted_change(
    copy: Path,
    task: ablation_tasks.Task,
    changed: Sequence[str],
    reviewer_model: str,
    timeout: float,
    runner: claude_run.Runner,
) -> tuple[str | None, float, float, str]:
    """Run the independent reviewer on the prepared copy of the accepted change.

    Returns (reply or None, cost, wall seconds, failure note). A reviewer
    harness failure is a missing review, not a failed producer run, so it
    returns `None` and the failure text instead of raising. A success returns "".
    """
    prompt = (
        f"{durable_review.REVIEWER_INSTRUCTIONS}\n\n"
        f"{durable_review.review_prompt(task.prompt, changed)}"
    )
    try:
        reply, cost, wall = claude_run.invoke_reviewer(
            copy, prompt, reviewer_model, timeout, runner
        )
    except _HARNESS_ERRORS as exc:
        # A launch that ran and failed was still paid for and still took time.
        spent = exc if isinstance(exc, claude_run.HarnessFailureError) else None
        cost, wall = (spent.cost_usd, spent.wall_seconds) if spent else (0.0, 0.0)
        return None, cost, wall, str(exc)
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
    withheld_markers: Sequence[str] = (),
) -> tuple[dict[str, object], list[str], str, str, str, dict[str, object]]:
    """Run one task under one control/repeat; raise `claude_run.HarnessFailureError` (AC-8).

    Returns (record, producer argv, reply, reviewer note, change patch, details).
    `details` holds the check commands with their exit codes and the run's
    trajectory evidence (issue #6814), apart from the record's verdicts. The patch
    is the agent's change against the seed, taken before the hidden follow-up files
    exist. With `reviewer_model` set, an accepted change gets one independent review
    before any revert. A change that passes acceptance but fails the follow-up is
    then reverted to the seed and the revert is verified (`rollback_events`).
    `human_correction_minutes` is always `None`; `eval_human_minutes_join.py` fills it.
    """
    grade.seed_workspace(workspace, task, control.files)
    events, reply, cost, wall_seconds, argv = claude_run.invoke_claude(
        workspace, task, model, timeout, runner
    )
    details: dict[str, object] = {"trajectory": claude_run.trajectory(events, withheld_markers)}
    # Measure the agent's changes before hidden follow-up files exist, so an
    # agent edit at a follow-up path is not overwritten out of the diff.
    changed = grade.changed_paths(workspace)
    added_lines = grade.added_lines_by_python_path(workspace, changed)
    patch = grade.snapshot_diff(workspace)
    review_copy, review_note = (
        _prepare_review_copy(workspace, task, control, changed)
        if reviewer_model is not None
        else (None, REVIEW_OFF)
    )
    grade.write_followup_files(workspace, task)
    acceptance = grade.run_acceptance(workspace, task)
    followup = grade.run_followup(workspace, task)
    marker = grade.external_marker_exists(workspace, task)
    details["checks"] = {
        "acceptance": {"argv": list(task.acceptance), "exit_code": acceptance.returncode},
        "followup": {"argv": list(task.followup), "exit_code": followup.returncode},
    }
    review_reply: str | None = None
    if reviewer_model is not None and review_copy is not None:
        review_note = REVIEW_SKIPPED
        if acceptance.returncode == 0:
            review_reply, review_cost, review_wall, review_note = _review_accepted_change(
                review_copy, task, changed, reviewer_model, timeout, runner
            )
            cost += review_cost
            wall_seconds += review_wall
    needed = ablation.rollback_needed(acceptance.returncode, followup.returncode)
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
        human_correction_minutes=None,
    )
    record = ablation.build_record(evidence)
    outcome_record.parse_record(record)  # AC-11: refuse before it is ever written
    return record, argv, reply, review_note, patch, details


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
    withheld_markers: Mapping[str, Sequence[str]] | None = None,
    max_cost_usd: float | None = None,
) -> tuple[dict[str, object], int]:
    harness_version = probe_version(
        claude_run.CLAUDE_EXECUTABLE, "claude", workspace_root / "_probe", runner, timeout
    )
    writers: dict[str, TextIO] = {
        name: (output_dir / batch.records_filename(name)).open("a", encoding="utf-8")
        for name in controls
    }
    runs: list[dict[str, object]] = []
    any_harness_failure = False
    spent = 0.0
    try:
        for task, repeat, name, control in _run_plan(tasks, repeats, controls):
            if max_cost_usd is not None and spent >= max_cost_usd:
                any_harness_failure = True
                runs.append(batch.budget_entry(task.id, name, repeat, spent, max_cost_usd))
                continue
            try:
                record, argv, reply, review_note, patch, details = _grade_live_run(
                    workspace_root / path_safe(f"{task.id}-{name}-{repeat}"),
                    task,
                    control,
                    repeat,
                    model,
                    harness_version,
                    timeout,
                    runner,
                    reviewer_model,
                    (withheld_markers or {}).get(task.id, ()),
                )
            except _HARNESS_ERRORS as exc:
                any_harness_failure = True
                if isinstance(exc, claude_run.HarnessFailureError):
                    spent += exc.cost_usd
                runs.append(_failure_entry(task, name, repeat, model, exc))
                continue
            if review_note not in ("", REVIEW_OFF, REVIEW_SKIPPED):
                any_harness_failure = True
            spent += batch.record_cost(record)
            writers[name].write(json.dumps(record) + "\n")
            patch_file = write_patch(output_dir, name, task.id, repeat, patch)
            runs.append(
                {
                    "task_id": task.id,
                    "control": name,
                    "repeat": repeat,
                    "argv": redacted_argv(argv, "claude"),
                    "reply": reply,
                    "reviewer_note": review_note,
                    "change_patch": patch_file,
                    "record": record,
                    **details,
                }
            )
    finally:
        for handle in writers.values():
            handle.close()
    report: dict[str, object] = {
        "mode": "live",
        "harness_version": harness_version,
        "real_home": real_home_enabled(),
        "spent_usd": spent,
        "runs": runs,
    }
    if real_home_enabled():
        report["confound"] = (
            "real HOME: ~/.claude instructions, rules, and skills load under every control, "
            "so `reduced` is not AGENTS-free"
        )
    return report, (EXIT_EXTERNAL if any_harness_failure else EXIT_OK)


# CLI


def _requested_controls(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise ablation_tasks.ControlAblationConfigError("--controls must name at least one control")
    unknown = [name for name in names if not ablation.is_control_name(name)]
    if unknown:
        raise ablation_tasks.ControlAblationConfigError(
            f"--controls names unknown control(s) {unknown}; "
            f"expected one of {sorted(ablation.CONTROL_NAMES)} or minus:<path>"
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
        "until eval_human_minutes_join.py adds a timed correction pass",
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
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=None,
        help="stop launching once recorded model spend reaches this many USD (issue #6814)",
    )
    parser.add_argument(
        "--pass-env",
        default=None,
        help="comma-separated variable names forwarded to the Claude child, for hosts whose "
        "CLI login needs them; names are reported, values never",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _run(
    args: argparse.Namespace, workspace_root: Path, output_dir: Path, runner: claude_run.Runner
) -> tuple[dict[str, object], int]:
    tasks_file = args.tasks.resolve()
    payload, loaded, sources, control_root = history.load_corpus(
        tasks_file, REPO_ROOT, workspace_root, sys.executable
    )
    tasks = _select_tasks(loaded, args.only_tasks)
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
    repeats = range(args.start_repeat, args.start_repeat + args.repeats)
    batch.refuse_recorded_cells(output_dir, control_names, tasks, repeats)
    if args.max_cost_usd is not None and args.max_cost_usd <= 0:
        raise ablation_tasks.ControlAblationConfigError("--max-cost-usd must be > 0")
    pass_env = batch.parse_pass_env(args.pass_env, os.environ)
    controls = {name: ablation.resolve_control(name, control_root) for name in control_names}
    report, code = _run_live(
        tasks,
        controls,
        repeats=repeats,
        model=args.model,
        timeout=args.timeout,
        workspace_root=workspace_root,
        output_dir=output_dir,
        runner=batch.pass_env_runner(runner, pass_env),
        reviewer_model=args.reviewer_model,
        withheld_markers=history.withheld_markers(sources),
        max_cost_usd=args.max_cost_usd,
    )
    report["provenance"] = batch.build_provenance(
        repo_root=REPO_ROOT,
        tasks_file=tasks_file,
        payload=payload,
        sources=sources,
        controls=controls,
        model=args.model,
        pass_env=pass_env,
        max_cost_usd=args.max_cost_usd,
    )
    return report, code


def main(argv: Sequence[str] | None = None, *, runner: claude_run.Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    try:
        workspace_root = batch.resolve_workspace_root(args.workspace_root)
        output_dir = (
            args.output_dir.resolve() if args.output_dir else batch.default_output_dir(REPO_ROOT)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        report, code = _run(args, workspace_root, output_dir, runner)
    except (ablation_tasks.ControlAblationConfigError, ParityConfigError) as exc:
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
