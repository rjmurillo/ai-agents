"""Batch bookkeeping for the control-ablation runner (issue #6814).

Records files, the resume guard, the spend cap, provenance, and operator
environment for the Claude child: everything about a batch that is not one run.

`build_provenance` names everything a reader needs to reproduce or audit a
batch: the runner commit, the task file and per-task hashes, each historical
task's source commits, and each control's exact files by hash, so a removed
configuration can be restored byte for byte. `child_env_runner` forwards named
operator variables to the Claude child; only the names reach the report.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from _control_ablation import CONTROL_NAMES, ControlFiles, is_control_name
from _control_ablation_history import TaskSource
from _control_ablation_tasks import ControlAblationConfigError, Task
from _run_changes import path_safe
from _runtime_harness import require_isolated_workspace_root

from scripts.redact_secrets import redact as redact_text

Runner = Callable[..., subprocess.CompletedProcess[str]]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_sha256(value: object) -> str:
    """Hash of `value` as sorted-key JSON, so key order never changes the hash."""
    return sha256_text(json.dumps(value, sort_keys=True, ensure_ascii=False))


def _git_text(repo_root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def runner_state(repo_root: Path) -> dict[str, object]:
    """The runner code's commit, and whether the checkout differed from it.

    Dirty means a tracked change or an untracked file: either can change the
    code that ran, so the named commit alone would not reproduce it. The hash
    covers the tracked diff plus each untracked file's path and bytes. `None`
    fields mean git could not say.
    """
    head = _git_text(repo_root, "rev-parse", "HEAD")
    diff = _git_text(repo_root, "diff", "HEAD")
    untracked = _git_text(repo_root, "ls-files", "--others", "--exclude-standard", "-z")
    if diff is None or untracked is None:
        return {
            "runner_commit": head.strip() or None if head is not None else None,
            "runner_tree_dirty": None,
            "runner_diff_sha256": None,
        }
    digest = hashlib.sha256(diff.encode("utf-8"))
    paths = sorted(path for path in untracked.split("\0") if path)
    for path in paths:
        digest.update(path.encode("utf-8") + b"\0")
        try:
            digest.update((repo_root / path).read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
    dirty = bool(diff) or bool(paths)
    return {
        "runner_commit": head.strip() or None if head is not None else None,
        "runner_tree_dirty": dirty,
        "runner_diff_sha256": digest.hexdigest() if dirty else None,
    }


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
        **runner_state(repo_root),
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


#: Variables the harness sets to isolate the child's profile, or that steer the
#: run itself. Forwarding one would silently undo that isolation.
_HARNESS_OWNED_ENV = frozenset(
    {"HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PATH", "TEMP", "TMP", "TMPDIR"}
)
_HARNESS_OWNED_PREFIXES = ("XDG_", "CLAUDE_CONFIG", "COPILOT_", "CODEX_", "EVAL_RUNTIME_")


def parse_pass_env(raw: str | None, environ: Mapping[str, str]) -> list[str]:
    """Names to forward; each must be set, and none may be one the harness owns.

    An unset name refuses so a typo cannot silently drop auth; a harness-owned
    name (HOME, CLAUDE_CONFIG_DIR, PATH, ...) refuses so forwarding cannot point
    the child back at the operator's real profile behind the report's back.
    """
    if raw is None:
        return []
    names = [name.strip() for name in raw.split(",") if name.strip()]
    owned = [n for n in names if n in _HARNESS_OWNED_ENV or n.startswith(_HARNESS_OWNED_PREFIXES)]
    if owned:
        raise ControlAblationConfigError(f"--pass-env may not forward harness-owned {owned}")
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


def record_cost(record: Mapping[str, object]) -> float | None:
    """The model cost a written record reports, or `None` when it reports none."""
    economics = record.get("economics")
    cost = economics.get("model_cost_usd") if isinstance(economics, Mapping) else None
    return float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None


class SpendGuard:
    """Running spend against `--max-cost-usd`, failing closed on unmeasured cost.

    A cell whose cost is unknown (a timeout, a failure that reported no cost, a
    record with no cost) may have spent anything, so once one happens under a cap
    no further cell launches. Without a cap nothing is ever blocked.
    """

    def __init__(self, cap: float | None) -> None:
        self.cap = cap
        self.spent = 0.0
        self.unmeasured = False

    @classmethod
    def resumed(cls, cap: float | None, output_dir: Path) -> SpendGuard:
        """A guard that starts from what earlier invocations into `output_dir` spent.

        A resumed batch (`--start-repeat` into the same directory) must not get a
        fresh cap. The start is the larger of the previous report's `spent_usd`
        (which counts failed launches too) and the sum of recorded costs, and an
        earlier unmeasured cost, or an unreadable record, keeps blocking.
        """
        guard = cls(cap)
        recorded = 0.0
        for path in sorted(output_dir.glob("records-*.jsonl")):
            try:
                rows = list(record_rows(path))
            except (OSError, ControlAblationConfigError):
                guard.unmeasured = True
                continue
            for row in rows:
                cost = record_cost(row)
                guard.unmeasured |= cost is None
                recorded += cost or 0.0
        previous = _previous_report(output_dir / "report.json")
        reported = previous.get("spent_usd")
        guard.spent = max(recorded, float(reported) if isinstance(reported, (int, float)) else 0.0)
        guard.unmeasured |= previous.get("spend_unmeasured") is True
        return guard

    def add_record(self, record: Mapping[str, object]) -> None:
        cost = record_cost(record)
        if cost is None:
            self.unmeasured = True
        else:
            self.spent += cost

    def add_failure(self, exc: BaseException) -> None:
        cost = getattr(exc, "cost_usd", 0.0)
        if isinstance(cost, (int, float)) and cost > 0:
            self.spent += float(cost)
        else:
            self.unmeasured = True

    def blocked_reason(self) -> str | None:
        if self.cap is None:
            return None
        if self.unmeasured:
            return "spend cap: an earlier cell's cost is unmeasured, so spend is unknown"
        if self.spent >= self.cap:
            return f"spend cap reached: {self.spent:.4f} >= {self.cap:.4f} USD"
        return None


def _previous_report(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"spend_unmeasured": True}
    return loaded if isinstance(loaded, dict) else {"spend_unmeasured": True}


def budget_entry(task_id: str, control: str, repeat: int, reason: str) -> dict[str, object]:
    """A cell the spend cap kept from launching: reported, never recorded as a result."""
    return {"task_id": task_id, "control": control, "repeat": repeat, "skipped": reason}


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def remove_base_trees(workspace_root: Path) -> None:
    """Delete every extracted `_base-<sha>` tree, whatever path left the run."""
    for path in workspace_root.glob("_base-*"):
        remove_tree(path)


#: A forwarded value naming a file at most this large is read so the file's
#: content (a token file) can be redacted too; larger files are not secrets.
_SECRET_FILE_MAX_BYTES = 16_384


def secret_literals(names: Sequence[str], environ: Mapping[str, str]) -> list[str]:
    """Literal strings to scrub from a report: each forwarded value, and a token file's content."""
    literals: list[str] = []
    for name in names:
        value = environ.get(name, "")
        if not value:
            continue
        literals.append(value)
        path = Path(value)
        try:
            if path.is_file() and path.stat().st_size <= _SECRET_FILE_MAX_BYTES:
                literals.append(path.read_text(encoding="utf-8", errors="replace").strip())
        except OSError:
            continue
    return sorted({item for item in literals if len(item) >= 8}, key=len, reverse=True)


def redact(value: object, literals: Sequence[str]) -> object:
    """Scrub forwarded secrets and known token shapes from every string in `value`.

    Agent replies, commands, and tool inputs are agent-written text that can echo
    a credential, so they pass through `scripts/redact_secrets.py` (hex kept, so
    commit SHAs survive) after the exact forwarded literals are replaced.
    """
    if isinstance(value, str):
        for literal in literals:
            value = value.replace(literal, "[redacted: forwarded secret]")
        return redact_text(value, include_hex=False).text
    if isinstance(value, Mapping):
        return {key: redact(item, literals) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, literals) for item in value]
    return value


def remove_cell(workspace: Path) -> None:
    """Delete a graded cell's workspace and its siblings (review copy, Claude profile).

    A graded historical cell holds the withheld check and the agent's change, so
    it must be gone before the next cell's agent could list or read it.
    """
    for path in (workspace, Path(f"{workspace}.review"), Path(f"{workspace}.claude-config")):
        remove_tree(path)


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


def requested_controls(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise ControlAblationConfigError("--controls must name at least one control")
    unknown = [name for name in names if not is_control_name(name)]
    if unknown:
        raise ControlAblationConfigError(
            f"--controls names unknown control(s) {unknown}; "
            f"expected one of {sorted(CONTROL_NAMES)} or minus:<path>"
        )
    return names


def select_tasks(tasks: list[Task], raw: str | None) -> list[Task]:
    """Keep only `--only-tasks` ids, in corpus order; an unknown id refuses."""
    if raw is None:
        return tasks
    wanted = {item.strip() for item in raw.split(",") if item.strip()}
    unknown = sorted(wanted - {task.id for task in tasks})
    if not wanted or unknown:
        raise ControlAblationConfigError(
            f"--only-tasks names unknown or no task id(s): {unknown or raw!r}"
        )
    return [task for task in tasks if task.id in wanted]
