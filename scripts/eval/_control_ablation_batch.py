"""Batch bookkeeping for the control-ablation runner (issue #6814).

Records files, the resume guard, the spend cap, provenance, and operator
environment for the Claude child: everything about a batch that is not one run.

`build_provenance` names everything a reader needs to reproduce or audit a
batch: the runner commit, the task file and per-task hashes, each historical
task's source commits, and each control's exact files by hash, so a removed
configuration can be restored byte for byte. `pass_env_runner` forwards named
operator variables to the Claude child; only the names reach the report.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from _control_ablation import ControlFiles
from _control_ablation_history import TaskSource
from _control_ablation_tasks import ControlAblationConfigError, Task
from _run_changes import path_safe
from _runtime_harness import require_isolated_workspace_root

Runner = Callable[..., subprocess.CompletedProcess[str]]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_sha256(value: object) -> str:
    """Hash of `value` as sorted-key JSON, so key order never changes the hash."""
    return sha256_text(json.dumps(value, sort_keys=True, ensure_ascii=False))


def runner_commit(repo_root: Path) -> str | None:
    """The commit the runner code was read from, or `None` when git cannot say."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = done.stdout.strip()
    return sha if done.returncode == 0 and sha else None


def control_manifest(control: ControlFiles) -> dict[str, object]:
    return {
        "context_bytes": control.context_bytes,
        "files": {path: sha256_text(text) for path, text in sorted(control.files.items())},
    }


def build_provenance(
    *,
    repo_root: Path,
    tasks_file: Path,
    payload: Mapping[str, Any],
    sources: Mapping[str, TaskSource],
    controls: Mapping[str, ControlFiles],
    model: str,
    pass_env: Sequence[str],
    max_cost_usd: float | None,
    interpreter: str,
) -> dict[str, object]:
    raw_tasks = payload.get("tasks")
    task_hashes = {
        str(task.get("id")): canonical_sha256(task)
        for task in (raw_tasks if isinstance(raw_tasks, list) else [])
        if isinstance(task, dict)
    }
    return {
        "runner_commit": runner_commit(repo_root),
        "tasks_file": str(tasks_file),
        "tasks_file_sha256": hashlib.sha256(tasks_file.read_bytes()).hexdigest(),
        "task_sha256": task_hashes,
        "sources": {task_id: asdict(source) for task_id, source in sources.items()},
        "controls": {name: control_manifest(control) for name, control in controls.items()},
        "model_requested": model,
        "pass_env": list(pass_env),
        "agent_path_first": str(Path(interpreter).parent),
        "max_cost_usd": max_cost_usd,
    }


def parse_pass_env(raw: str | None, environ: Mapping[str, str]) -> list[str]:
    """Names to forward; each must be set, so a typo cannot silently drop auth."""
    if raw is None:
        return []
    names = [name.strip() for name in raw.split(",") if name.strip()]
    missing = [name for name in names if name not in environ]
    if not names or missing:
        raise ControlAblationConfigError(f"--pass-env names unset or no variable(s): {missing}")
    return names


def child_env_runner(runner: Runner, names: Sequence[str], interpreter: str) -> Runner:
    """Wrap `runner` so every child env starts PATH at `interpreter`'s directory.

    The checks run with the runner's interpreter (`{python}`), so the agent's
    `python3` must be that interpreter too, or the agent cannot run the checks it
    is graded by: launched outside `uv run`, PATH would resolve a bare system
    Python without pytest (issue #6814, first pilot). The named operator
    variables are forwarded too, for hosts whose Claude CLI login needs variables
    `runtime_env`'s allowlist drops; values are read at call time and never
    written to the report.
    """
    bin_dir = str(Path(interpreter).parent)

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs.get("env")
        if isinstance(env, dict):
            path = env.get("PATH", "")
            entries = [bin_dir, *(e for e in str(path).split(os.pathsep) if e and e != bin_dir)]
            forwarded = {name: os.environ[name] for name in names}
            kwargs["env"] = {**env, **forwarded, "PATH": os.pathsep.join(entries)}
        return runner(argv, **kwargs)

    return run


def record_cost(record: Mapping[str, object]) -> float:
    """The model cost a written record reports, for the batch's running spend."""
    economics = record.get("economics")
    cost = economics.get("model_cost_usd") if isinstance(economics, Mapping) else None
    return float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else 0.0


def budget_entry(
    task_id: str, control: str, repeat: int, spent: float, cap: float
) -> dict[str, object]:
    """A cell the spend cap kept from launching: reported, never recorded as a result."""
    return {
        "task_id": task_id,
        "control": control,
        "repeat": repeat,
        "skipped": f"spend cap reached: {spent:.4f} >= {cap:.4f} USD",
    }


def records_filename(control: str) -> str:
    """`records-<control>.jsonl` with the name made path-safe (`minus:` holds a path)."""
    return f"records-{path_safe(control)}.jsonl"


def refuse_recorded_cells(
    output_dir: Path,
    control_names: Sequence[str],
    tasks: Sequence[Task],
    repeats: range,
) -> None:
    """Refuse a batch that would append a (task, repeat) its records already hold.

    Records append, so a rerun into the same `--output-dir` would duplicate a
    cell and `eval_durable_outcome.py` would refuse the file. Resume with
    `--only-tasks` and `--start-repeat` instead.
    """
    planned = {(task.id, repeat) for task in tasks for repeat in repeats}
    for name in control_names:
        path = output_dir / records_filename(name)
        if not path.is_file():
            continue
        recorded = {(row["task_id"], row["repeat"]) for row in record_rows(path)}
        clash = sorted(planned & recorded)
        if clash:
            raise ControlAblationConfigError(
                f"{path} already records {clash}; use a new --output-dir or --start-repeat"
            )


def record_rows(path: Path) -> Iterator[dict[str, object]]:
    """Yield each JSON row of a records file; blank lines are skipped, bad JSON refuses."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except ValueError as exc:
            raise ControlAblationConfigError(
                f"{path} line {number} is not valid JSON: {exc}"
            ) from exc


def default_output_dir(repo_root: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    return repo_root / "artifacts" / "control-ablation" / run_id


def resolve_workspace_root(raw: Path | None) -> Path:
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
