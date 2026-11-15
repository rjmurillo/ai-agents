#!/usr/bin/env python3
"""Compare continued analyst investigation with an independent-thinker handoff (issue #7350).

Reuses the #6814 historical harness. Each cell seeds a fresh workspace from a real
pre-fix commit, then runs rounds of (read-only investigator launch, producer launch,
visible reproduction). Arm A investigates with the analyst role text and a
"continue" instruction. Arm B investigates with the independent-thinker role text
and a bounded handoff instruction. Producer launches, facts, tools, model, effort,
and correction budget are identical. The held-out check runs only after the last
round, and a model judge never overrides a deterministic failure.

`--dry-run` makes no model call: each task's reproduction must be red on the base,
the shipped fix must pass and a plausible-wrong fix must fail the held-out check.

Exit codes: 0 ok; 1 dry-run discrimination failure; 2 config; 3 external (a cell
failed or was invalid); 4 auth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

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
import _handoff_strategy as hs  # noqa: E402
import _outcome_record as outcome_record  # noqa: E402
from _isolated_claude_login import IsolatedLoginError, isolated_login_values  # noqa: E402
from _run_changes import path_safe, write_patch  # noqa: E402
from _runtime_harness import REAL_HOME_ENV, probe_version, real_home_enabled  # noqa: E402
from _runtime_parity import ParityConfigError  # noqa: E402

EXIT_OK, EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL, EXIT_AUTH = 0, 1, 2, 3, 4
DEFAULT_TASKS = Path(__file__).parent / "examples" / "handoff-strategy-tasks.json"
DEFAULT_TIMEOUT = 600.0
_HARNESS_ERRORS = (
    claude_run.HarnessFailureError,
    grade.WorkspaceError,
    subprocess.SubprocessError,
    OSError,
)


def cell_dir(workspace_root: Path, task_id: str, repeat: int) -> Path:
    """Arm-neutral cell path: the reproduction's traceback prints it, so it must not name the arm.

    Cells run one at a time and each is deleted after grading, so both arms reuse it.
    """
    return workspace_root / path_safe(f"{task_id}-r{repeat}")


def _file_state(workspace: Path) -> dict[str, str]:
    """Non-incidental changed paths mapped to content hashes, to detect an investigator write."""
    state: dict[str, str] = {}
    for path in grade.changed_paths(workspace):
        if ablation._is_incidental_path(path):
            continue
        target = workspace / path
        state[path] = (
            hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "deleted"
        )
    return state


def _argv_summary(argv: Sequence[str]) -> list[str]:
    """The argv with the prompt and role text replaced by hashes, so a report stays small."""
    out: list[str] = []
    hide = False
    for item in argv:
        out.append(f"<sha256 {hs.sha256_text(item)}>" if hide else item)
        hide = item in ("--print", "--append-system-prompt")
    return out


class _Cell:
    """Accumulates one cell's launches, spend, and time."""

    def __init__(
        self, model: str, timeout: float, runner: claude_run.Runner, workspace: Path
    ) -> None:
        self.model, self.timeout, self.runner, self.workspace = model, timeout, runner, workspace
        self.cost = 0.0
        self.wall = 0.0
        self.failures = 0
        self.launches: list[dict[str, object]] = []

    def launch(self, role: str, prompt: str, markers: Sequence[str], **kwargs: object) -> str:
        try:
            events, reply, cost, wall, argv = claude_run.invoke_launch(
                self.workspace, prompt, self.model, self.timeout, self.runner, **kwargs
            )
        except claude_run.HarnessFailureError as exc:
            self.cost += exc.cost_usd
            self.wall += exc.wall_seconds
            raise
        self.cost += cost
        self.wall += wall
        self.failures += claude_run.tool_failures(events)
        trajectory = claude_run.trajectory(events, markers)
        self.launches.append(
            {
                "role": role,
                "argv": _argv_summary(argv),
                "cost_usd": cost,
                "wall_seconds": round(wall, 2),
                "reply": reply,
                "trajectory": trajectory,
            }
        )
        return reply


def run_cell(
    task: ablation_tasks.Task,
    brief: hs.Brief,
    arm: str,
    repeat: int,
    control: ablation.ControlFiles,
    *,
    role: str,
    model: str,
    effort: str | None,
    harness_version: str,
    timeout: float,
    workspace_root: Path,
    runner: claude_run.Runner,
    markers: Sequence[str],
) -> tuple[dict[str, object], dict[str, object], str, _Cell]:
    """Run one task x arm x repeat; return (entry, record, patch, cell).

    Raises `HarnessFailureError` when a launch fails or the base is not a stalled state.
    """
    workspace = cell_dir(workspace_root, task.id, repeat)
    grade.seed_workspace(workspace, task, control.files)
    cell = _Cell(model, timeout, runner, workspace)
    base = grade.run_acceptance(workspace, task)
    if base.returncode == 0:
        raise claude_run.HarnessFailureError(
            "reproduction is green on the base: not a stalled state"
        )
    facts = hs.facts_block(task, brief, base.stdout + base.stderr)
    effort_args = ["--effort", effort] if effort else []
    findings = feedback = ""
    invalid = ""
    repair_turns = 0
    reply = ""
    for round_index in range(hs.REPAIR_ROUNDS + 1):
        before = _file_state(workspace)
        findings = cell.launch(
            f"investigator:{arm}:r{round_index}",
            hs.investigator_prompt(arm, facts, findings, feedback),
            markers,
            tools=hs.INVESTIGATOR_TOOLS,
            allowed_tools=hs.INVESTIGATOR_ALLOWED,
            extra_args=["--append-system-prompt", role, *effort_args],
        )
        if _file_state(workspace) != before:
            invalid = "investigator changed the workspace"
            break
        reply = cell.launch(
            f"producer:r{round_index}",
            hs.producer_prompt(facts, findings, feedback),
            markers,
            extra_args=effort_args,
        )
        acceptance = grade.run_acceptance(workspace, task)
        if acceptance.returncode == 0 or round_index == hs.REPAIR_ROUNDS:
            break
        feedback = (acceptance.stdout + acceptance.stderr)[-hs.FEEDBACK_CHARS :]
        repair_turns += 1
    hits = [h for launch in cell.launches for h in launch["trajectory"]["withheld_marker_hits"]]
    if hits:
        invalid = "tool call named withheld evidence"
    changed = grade.changed_paths(workspace)
    added = grade.added_lines_by_python_path(workspace, changed)
    patch = grade.snapshot_diff(workspace)
    grade.write_followup_files(workspace, task)
    acceptance = grade.run_acceptance(workspace, task)
    followup = grade.run_followup(workspace, task)
    marker = grade.external_marker_exists(workspace, task)
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
        added_lines_by_path=added,
        tool_failures=cell.failures,
        acceptance_exit_code=acceptance.returncode,
        followup_exit_code=followup.returncode,
        followup_output=followup.stdout + "\n" + followup.stderr,
        external_marker_exists=marker,
        model_cost_usd=cell.cost,
        wall_seconds=cell.wall,
        rollback_events=ablation.rollback_events(needed, reverted),
        human_correction_minutes=None,
    )
    record = ablation.build_record(evidence)
    outcome_record.parse_record(record)
    scope = ablation.scope_violations(changed, task.allowed_paths)
    entry: dict[str, object] = {
        "task_id": task.id,
        "arm": arm,
        "repeat": repeat,
        "valid": not invalid,
        "invalid_reason": invalid or None,
        "base_acceptance_exit": base.returncode,
        "acceptance_exit": acceptance.returncode,
        "heldout_exit": followup.returncode,
        "accepted": not invalid
        and acceptance.returncode == 0
        and followup.returncode == 0
        and scope == 0
        and not marker,
        "regression": acceptance.returncode == 0 and followup.returncode != 0,
        "scope_violations": scope,
        "repair_turns": repair_turns,
        "cost_usd": cell.cost,
        "wall_seconds": round(cell.wall, 2),
        "tool_failures": cell.failures,
        "human_correction_minutes": None,
        "blocking_findings": None,
        "checks": {
            "base": {"argv": list(task.acceptance), "exit_code": base.returncode},
            "acceptance": {"argv": list(task.acceptance), "exit_code": acceptance.returncode},
            "heldout": {"argv": list(task.followup), "exit_code": followup.returncode},
        },
        "launches": cell.launches,
    }
    return entry, record, patch, cell


def _dry_run(corpus: hs.HandoffCorpus, workspace_root: Path) -> tuple[dict[str, object], bool]:
    report, ok = dry_run.run_dry_run(corpus.tasks, workspace_root)
    red: dict[str, int] = {}
    for task in corpus.tasks:
        workspace = workspace_root / f"{task.id}-base-red"
        grade.seed_workspace(workspace, task, {})
        red[task.id] = grade.run_acceptance(workspace, task).returncode
    all_red = all(code != 0 for code in red.values())
    report["base_acceptance_exit"] = red
    report["base_red"] = all_red
    report["status"] = "PASS" if ok and all_red else "FAIL"
    return report, ok and all_red


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--effort", default=None, help="passed to every launch, both arms")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-cells", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--real-home", action="store_true")
    parser.add_argument("--pass-env", default=None)
    parser.add_argument("--only-tasks", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _controls(corpus: hs.HandoffCorpus, workspace_root: Path) -> dict[str, ablation.ControlFiles]:
    """`full` control resolved at each task's own base commit, then the base tree is removed."""
    controls: dict[str, ablation.ControlFiles] = {}
    for task in corpus.tasks:
        sha = corpus.sources[task.id].base_sha
        root = history.materialize_tree(REPO_ROOT, sha, workspace_root / f"_base-{sha[:12]}")
        controls[task.id] = ablation.resolve_control("full", root)
        batch.remove_tree(root)
    return controls


def _run_live(
    args: argparse.Namespace,
    corpus: hs.HandoffCorpus,
    workspace_root: Path,
    output_dir: Path,
    runner: claude_run.Runner,
) -> tuple[dict[str, object], int]:
    if args.real_home:
        os.environ[REAL_HOME_ENV] = "1"
    tasks = batch.select_tasks(corpus.tasks, args.only_tasks)
    cells = len(tasks) * len(hs.ARMS) * args.repeats
    if args.repeats < 1 or args.repeats > 3 or cells > args.max_cells:
        raise ablation_tasks.ControlAblationConfigError(
            f"{cells} cells with {args.repeats} repeats exceeds the frozen ceilings"
        )
    cap = args.max_cost_usd
    if cap is not None and (not math.isfinite(cap) or cap <= 0):
        raise ablation_tasks.ControlAblationConfigError("--max-cost-usd must be finite and > 0")
    pass_env = batch.parse_pass_env(args.pass_env, os.environ)
    roles = {arm: hs.role_text(REPO_ROOT, arm) for arm in hs.ARMS}
    controls = _controls(corpus, workspace_root)
    markers = history.withheld_markers(corpus.sources, REPO_ROOT)
    wrapped = batch.child_env_runner(runner, pass_env, sys.executable)
    version = probe_version(
        claude_run.CLAUDE_EXECUTABLE, "claude", workspace_root / "_probe", wrapped, args.timeout
    )
    guard = batch.SpendGuard.resumed(cap, output_dir)
    literals = [
        *batch.secret_literals(pass_env, os.environ),
        *isolated_login_values(claude_run.CLAUDE_EXECUTABLE, skip=real_home_enabled()),
    ]
    entries: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for task in tasks:
        for repeat in range(args.repeats):
            order = hs.ARMS if repeat % 2 == 0 else tuple(reversed(hs.ARMS))
            for arm in order:
                blocked = guard.blocked_reason()
                if blocked:
                    failures.append(
                        {"task_id": task.id, "arm": arm, "repeat": repeat, "reason": blocked}
                    )
                    continue
                try:
                    entry, record, patch, cell = run_cell(
                        task,
                        corpus.briefs[task.id],
                        arm,
                        repeat,
                        controls[task.id],
                        role=roles[arm],
                        model=args.model,
                        effort=args.effort,
                        harness_version=version,
                        timeout=args.timeout,
                        workspace_root=workspace_root,
                        runner=wrapped,
                        markers=markers[task.id],
                    )
                except _HARNESS_ERRORS as exc:
                    guard.add_failure(exc)
                    failures.append(
                        {"task_id": task.id, "arm": arm, "repeat": repeat, "reason": str(exc)}
                    )
                    continue
                finally:
                    batch.remove_cell(cell_dir(workspace_root, task.id, repeat))
                guard.add_record(record)
                with (output_dir / batch.records_filename(arm)).open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
                entry["change_patch"] = write_patch(
                    output_dir, arm, task.id, repeat, str(batch.redact(patch, literals))
                )
                entries.append(batch.redact(entry, literals))  # type: ignore[arg-type]
    stall = {t.id for t in tasks if corpus.stall[t.id]}
    decision = hs.decide(entries, stall, {t.id for t in tasks} - stall, cells)
    report: dict[str, object] = {
        "mode": "live",
        "harness_version": version,
        "real_home": real_home_enabled(),
        "effort": args.effort or "harness default, not set",
        "spent_usd": guard.spent,
        "spend_unmeasured": guard.unmeasured,
        "entries": entries,
        "failures": failures,
        "decision": decision,
        "provenance": {
            **batch.runner_state(REPO_ROOT),
            "tasks_file_sha256": hashlib.sha256(args.tasks.read_bytes()).hexdigest(),
            "task_sha256": {
                str(t.get("id")): batch.canonical_sha256(t)
                for t in json.loads(args.tasks.read_text(encoding="utf-8"))["tasks"]
            },
            "sources": {
                k: v.__dict__ if hasattr(v, "__dict__") else str(v)
                for k, v in corpus.sources.items()
            },
            "role_files": {arm: hs.ROLE_FILES[arm] for arm in hs.ARMS},
            "role_sha256": {arm: hs.sha256_text(roles[arm]) for arm in hs.ARMS},
            "prompt_templates": hs.prompt_template_hashes(),
            "controls": {tid: batch.control_manifest(c) for tid, c in controls.items()},
            "model_requested": args.model,
            "pass_env": pass_env,
            "agent_path_first": str(Path(sys.executable).parent),
            "max_cost_usd": cap,
            "repair_rounds": hs.REPAIR_ROUNDS,
            "started_unix": int(time.time()),
        },
    }
    return report, (EXIT_EXTERNAL if failures or not all(e["valid"] for e in entries) else EXIT_OK)


def main(argv: Sequence[str] | None = None, *, runner: claude_run.Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    workspace_root = None
    try:
        skip = args.dry_run or args.real_home or real_home_enabled()
        isolated_login_values(claude_run.CLAUDE_EXECUTABLE, skip=skip)
        workspace_root = batch.resolve_workspace_root(args.workspace_root)
        output_dir = (
            args.output_dir.resolve() if args.output_dir else batch.default_output_dir(REPO_ROOT)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(args.tasks.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ablation_tasks.ControlAblationConfigError(
                f"cannot read {args.tasks}: {exc}"
            ) from exc
        corpus = hs.load_tasks(payload, REPO_ROOT, sys.executable)
        if args.dry_run:
            report, ok = _dry_run(corpus, workspace_root)
            code = EXIT_OK if ok else EXIT_LOGIC
        else:
            report, code = _run_live(args, corpus, workspace_root, output_dir, runner)
    except (ablation_tasks.ControlAblationConfigError, ParityConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except IsolatedLoginError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_AUTH
    except (*_HARNESS_ERRORS, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    finally:
        if workspace_root is not None:
            batch.remove_base_trees(workspace_root)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "entries"}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
