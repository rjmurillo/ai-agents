#!/usr/bin/env python3
"""Run a code-task corpus under the full and a reduced control plane (REQ-043).

Compares the current control plane (every file `always_loaded` loads for
Claude Code) against a reduced one (none) on identical tasks, model, and
retry/correction budget (issue #5768). `--dry-run` proves each task's
grader discriminates a known-good fix from a known-bad one without any
model call. A live run writes one `OutcomeRecord` per run to
`records-<control>.jsonl` under `--output-dir`, which `eval_durable_outcome.py
--baseline` then compares.

Exit codes follow AGENTS.md and DESIGN-041: 0 ok; 1 dry-run discrimination
failure; 2 config (bad task file, unknown control, budget exceeded,
unisolated workspace root); 3 external (CLI missing, timeout, unparsable
stream, missing cost, model mismatch).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

import _control_ablation as ablation
import _control_ablation_claude as claude_run
import _control_ablation_grade as grade
import _control_ablation_tasks as ablation_tasks
import _durable_outcome as durable_outcome
import _outcome_record as outcome_record
from _runtime_harness import probe_version, require_isolated_workspace_root
from _runtime_output import (
    redacted_argv,
)
from _runtime_parity import ParityConfigError

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = Path(__file__).parent / "examples" / "control-ablation-tasks.json"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_TIMEOUT = 900.0
DEFAULT_MAX_RUNS = 30
DRY_RUN_KINDS = ("known_good", "known_bad")
_HARNESS_ERRORS = (claude_run.HarnessFailureError, subprocess.SubprocessError, OSError)





# ---------------------------------------------------------------------------
# Dry run (REQ-043 AC-2)
# ---------------------------------------------------------------------------


def _grade_dry_run_control(
    workspace: Path, task: ablation_tasks.Task, control: ablation_tasks.TaskControl
) -> ablation.RunEvidence:
    grade.seed_workspace(workspace, task, {})
    grade.apply_control_files(workspace, control.files)
    acceptance = grade.run_acceptance(workspace, task)
    grade.write_followup_files(workspace, task)
    followup = grade.run_followup(workspace, task)
    changed = grade.changed_paths(workspace)
    return ablation.RunEvidence(
        task=task,
        control=ablation.ControlFiles(name="dry-run", files={}, context_bytes=0),
        repeat=0,
        model="dry-run",
        harness_version="dry-run",
        reply=control.response,
        changed_paths=changed,
        added_lines_by_path=grade.added_lines_by_python_path(workspace, changed),
        tool_failures=0,
        acceptance_exit_code=acceptance.returncode,
        followup_exit_code=followup.returncode,
        followup_output=followup.stdout + "\n" + followup.stderr,
        external_marker_exists=grade.external_marker_exists(workspace, task),
        model_cost_usd=0.0,
        wall_seconds=0.0,
    )


def _run_dry_run(
    tasks: Sequence[ablation_tasks.Task], workspace_root: Path
) -> tuple[dict[str, object], int]:
    """AC-2: apply every task's known_good/known_bad controls, grade for real.

    Dry-run records are not written to `records-<control>.jsonl`: AC-11
    scopes that file to live runs. Each run's record still appears in
    `report.json` for inspection.
    """
    runs: list[dict[str, object]] = []
    good_total = good_accepted = bad_total = bad_accepted = 0
    for task in tasks:
        for kind in DRY_RUN_KINDS:
            workspace = workspace_root / f"{task.id}-{kind}"
            evidence = _grade_dry_run_control(workspace, task, task.controls[kind])
            record = ablation.build_record(evidence)
            verdict = durable_outcome.classify(outcome_record.parse_record(record))
            runs.append(
                {"task_id": task.id, "kind": kind, "verdict": verdict.value, "record": record}
            )
            is_accepted_durable = verdict is durable_outcome.Verdict.ACCEPTED_DURABLE
            if kind == "known_good":
                good_total += 1
                good_accepted += int(is_accepted_durable)
            else:
                bad_total += 1
                bad_accepted += int(is_accepted_durable)
    ok = good_accepted == good_total and bad_accepted == 0
    report = {
        "mode": "dry-run",
        "runs": runs,
        "known_good_accepted_durable": good_accepted,
        "known_good_total": good_total,
        "known_bad_accepted_durable": bad_accepted,
        "known_bad_total": bad_total,
        "status": "PASS" if ok else "FAIL",
    }
    return report, (EXIT_OK if ok else EXIT_LOGIC)


# ---------------------------------------------------------------------------
# Live run (REQ-043 AC-3, AC-4, AC-8, AC-11)
# ---------------------------------------------------------------------------


def _grade_live_run(
    workspace: Path,
    task: ablation_tasks.Task,
    control: ablation.ControlFiles,
    repeat: int,
    model: str,
    harness_version: str,
    timeout: float,
    runner: claude_run.Runner,
    auth_file: Path | None,
) -> tuple[dict[str, object], list[str], str]:
    """Run one task under one control/repeat; raise `claude_run.HarnessFailureError` (AC-8)."""
    grade.seed_workspace(workspace, task, control.files)
    events, reply, cost, wall_seconds, argv = claude_run.invoke_claude(
        workspace, task, model, timeout, runner, auth_file
    )
    grade.write_followup_files(workspace, task)
    acceptance = grade.run_acceptance(workspace, task)
    followup = grade.run_followup(workspace, task)
    changed = grade.changed_paths(workspace)
    evidence = ablation.RunEvidence(
        task=task,
        control=control,
        repeat=repeat,
        model=model,
        harness_version=harness_version,
        reply=reply,
        changed_paths=changed,
        added_lines_by_path=grade.added_lines_by_python_path(workspace, changed),
        tool_failures=claude_run.tool_failures(events),
        acceptance_exit_code=acceptance.returncode,
        followup_exit_code=followup.returncode,
        followup_output=followup.stdout + "\n" + followup.stderr,
        external_marker_exists=grade.external_marker_exists(workspace, task),
        model_cost_usd=cost,
        wall_seconds=wall_seconds,
    )
    record = ablation.build_record(evidence)
    outcome_record.parse_record(record)  # AC-11: refuse before it is ever written
    return record, argv, reply


def _run_live(
    tasks: Sequence[ablation_tasks.Task],
    controls: Mapping[str, ablation.ControlFiles],
    *,
    repeats: int,
    model: str,
    timeout: float,
    workspace_root: Path,
    output_dir: Path,
    runner: claude_run.Runner,
    auth_file: Path | None = None,
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
        # DESIGN-041 "Run sequence (live)": "Runs interleave: for each task,
        # for each repeat, for each control."
        for task in tasks:
            for repeat in range(repeats):
                for name, control in controls.items():
                    workspace = workspace_root / f"{task.id}-{name}-{repeat}"
                    planned_argv = claude_run.claude_argv(model, task.prompt)
                    argv_for_report = redacted_argv(planned_argv, "claude")
                    try:
                        record, argv, reply = _grade_live_run(
                            workspace,
                            task,
                            control,
                            repeat,
                            model,
                            harness_version,
                            timeout,
                            runner,
                            auth_file,
                        )
                    except _HARNESS_ERRORS as exc:
                        any_harness_failure = True
                        runs.append(
                            {
                                "task_id": task.id,
                                "control": name,
                                "repeat": repeat,
                                "argv": argv_for_report,
                                "harness_failure": str(exc),
                            }
                        )
                        continue
                    writers[name].write(json.dumps(record) + "\n")
                    runs.append(
                        {
                            "task_id": task.id,
                            "control": name,
                            "repeat": repeat,
                            "argv": redacted_argv(argv, "claude"),
                            "reply": reply,
                            "record": record,
                        }
                    )
    finally:
        for handle in writers.values():
            handle.close()
    report = {"mode": "live", "harness_version": harness_version, "runs": runs}
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


def _default_output_dir() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    return REPO_ROOT / "artifacts" / "control-ablation" / run_id


def _resolve_workspace_root(raw: Path | None) -> Path:
    """Resolve and validate `--workspace-root` before creating anything.

    `require_isolated_workspace_root` runs before `mkdir` (not after): a
    refused root must not leave a stray directory behind in a location the
    check just said is unsafe, such as inside this repository's own tree.
    """
    root = raw.resolve() if raw else Path(tempfile.mkdtemp(prefix="control-ablation-"))
    require_isolated_workspace_root(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--controls", default="full,reduced")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-runs", type=int, default=DEFAULT_MAX_RUNS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--claude-auth-file",
        type=Path,
        default=None,
        help=(
            "Opt-in: copy this Claude Code .credentials.json into each live run's "
            "isolated CLAUDE_CONFIG_DIR for the duration of the Claude call."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _run(
    args: argparse.Namespace, workspace_root: Path, output_dir: Path, runner: claude_run.Runner
) -> tuple[dict[str, object], int]:
    tasks = ablation_tasks.load_tasks_file(args.tasks.resolve())
    if args.dry_run:
        return _run_dry_run(tasks, workspace_root)
    control_names = _requested_controls(args.controls)
    total_runs = len(tasks) * len(control_names) * args.repeats
    if total_runs > args.max_runs:
        raise ablation_tasks.ControlAblationConfigError(
            f"{total_runs} runs (tasks x controls x repeats) exceeds --max-runs {args.max_runs}; "
            "refusing before any model call (AC-3)"
        )
    auth_file = args.claude_auth_file.resolve() if args.claude_auth_file else None
    if auth_file is not None and not auth_file.is_file():
        raise ablation_tasks.ControlAblationConfigError(
            f"--claude-auth-file {auth_file} is not a regular file"
        )
    controls = {name: ablation.resolve_control(name, REPO_ROOT) for name in control_names}
    return _run_live(
        tasks,
        controls,
        repeats=args.repeats,
        model=args.model,
        timeout=args.timeout,
        workspace_root=workspace_root,
        output_dir=output_dir,
        runner=runner,
        auth_file=auth_file,
    )


def main(argv: Sequence[str] | None = None, *, runner: claude_run.Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    try:
        workspace_root = _resolve_workspace_root(args.workspace_root)
        output_dir = (args.output_dir.resolve() if args.output_dir else _default_output_dir())
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
