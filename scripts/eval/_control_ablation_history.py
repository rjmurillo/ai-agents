"""Historical issue-to-fix tasks for the control ablation (issue #6814).

A schema_version 2 task file names a real, already-shipped issue instead of
inline fixture files: the pre-fix `base_sha` the agent works on, the `fix_sha`
that shipped, the `seed_paths` copied from the base, and the `withheld_files`
copied from the fix only after the agent exits. Loading reads those blobs from
this repository's git objects and returns ordinary `Task` values, so the
seed, grade, and record path in `eval_control_ablation.py` stays unchanged.

The agent's workspace is a fresh `git init` of the seeded files, never a clone
or worktree, so it carries no history that would reveal the shipped fix.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tarfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _control_ablation_tasks import ControlAblationConfigError, Task, load_task, load_tasks

SCHEMA_VERSION = 2
CASE = "historical_fix"
#: An argv element equal to this is replaced with the runner's interpreter, so
#: a check runs with the same locked environment (pytest included) as the runner.
PYTHON_TOKEN = "{python}"
GIT_TIMEOUT = 120.0
#: A full SHA-1 or SHA-256 object name: never a ref that can move, never an option.
_FULL_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

_TASK_KEYS = frozenset(
    {
        "id",
        "case",
        "prompt",
        "source",
        "allowed_paths",
        "acceptance",
        "followup",
        "external_marker",
        "response_checks",
        "controls",
        "notes",
    }
)
_SOURCE_KEYS = frozenset(
    {"repository", "issue", "fix_pr", "base_sha", "fix_sha", "seed_paths", "withheld_files"}
)
_CONTROL_KEYS = frozenset({"files_from_fix", "edits", "response"})
_GIT_CONTEXT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


@dataclass(frozen=True, slots=True)
class TaskSource:
    """Where a historical task came from; copied verbatim into the report."""

    repository: str
    issue: int
    fix_pr: int
    base_sha: str
    fix_sha: str
    seed_paths: tuple[str, ...]
    withheld_files: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class HistoricalCorpus:
    tasks: list[Task]
    sources: Mapping[str, TaskSource]

    @property
    def base_sha(self) -> str:
        """The one base commit every task shares; controls are read from it."""
        return next(iter(self.sources.values())).base_sha


def is_historical(payload: Mapping[str, Any]) -> bool:
    return payload.get("schema_version") == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Git object reads
# ---------------------------------------------------------------------------


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in _GIT_CONTEXT_VARIABLES:
        env.pop(name, None)
    return env


def _git_bytes(repo_root: Path, args: Sequence[str]) -> bytes:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            env=_git_env(),
            capture_output=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ControlAblationConfigError(f"git {args[0]} could not run: {exc}") from exc
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", errors="replace").strip()
        raise ControlAblationConfigError(
            f"git {' '.join(args)} failed: {detail}. A shallow clone may need "
            "`git fetch --depth=N origin main` to hold the commit"
        )
    return done.stdout


def _decode(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ControlAblationConfigError(f"{label} is not UTF-8 text: {exc}") from exc


def read_blob(repo_root: Path, sha: str, path: str) -> str:
    return _decode(_git_bytes(repo_root, ["show", f"{sha}:{path}"]), f"{sha}:{path}")


def read_tree(repo_root: Path, sha: str, paths: Sequence[str]) -> dict[str, str]:
    """Every regular file under `paths` at `sha`, as text keyed by repo-relative path."""
    archive = _git_bytes(repo_root, ["archive", "--format=tar", sha, "--", *paths])
    files: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            files[member.name] = _decode(handle.read(), f"{sha}:{member.name}")
    if not files:
        raise ControlAblationConfigError(f"{sha} holds no file under {list(paths)}")
    return files


def materialize_tree(repo_root: Path, sha: str, destination: Path) -> Path:
    """Extract the whole tree at `sha` into `destination` (for control resolution)."""
    archive = _git_bytes(repo_root, ["archive", "--format=tar", sha])
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        extract_regular_files(tar, destination)
    return destination


def extract_regular_files(tar: tarfile.TarFile, destination: Path) -> None:
    """Write each regular file member under `destination`, refusing any that escapes it.

    Links and special files are skipped: control resolution reads regular files
    only, and a link is the other way a member can point outside the tree (CWE-22).
    """
    root = destination.resolve()
    for member in tar.getmembers():
        if not member.isfile():
            continue
        target = (root / member.name).resolve()
        if not target.is_relative_to(root):
            raise ControlAblationConfigError(f"archive member escapes the tree: {member.name!r}")
        handle = tar.extractfile(member)
        if handle is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(handle.read())


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _require_text(raw: Mapping[str, Any], key: str, path: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ControlAblationConfigError(
            f"{path}.{key}: expected a non-empty string, got {value!r}"
        )
    return value


def _require_int(raw: Mapping[str, Any], key: str, path: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ControlAblationConfigError(f"{path}.{key}: expected an integer, got {value!r}")
    return value


def _check_keys(raw: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = raw.keys() - allowed
    if unknown:
        raise ControlAblationConfigError(f"{path}: unknown key(s) {sorted(unknown)}")


def _load_source(raw: object, path: str) -> TaskSource:
    if not isinstance(raw, dict):
        raise ControlAblationConfigError(f"{path}: expected an object")
    _check_keys(raw, _SOURCE_KEYS, path)
    seed_paths = raw.get("seed_paths")
    withheld = raw.get("withheld_files")
    if not isinstance(seed_paths, list) or not seed_paths:
        raise ControlAblationConfigError(f"{path}.seed_paths must be a non-empty array")
    if not isinstance(withheld, dict) or not withheld:
        raise ControlAblationConfigError(f"{path}.withheld_files must be a non-empty object")
    for key in ("base_sha", "fix_sha"):
        if not _FULL_SHA.fullmatch(_require_text(raw, key, path)):
            raise ControlAblationConfigError(f"{path}.{key} must be a full hex commit SHA")
    return TaskSource(
        repository=_require_text(raw, "repository", path),
        issue=_require_int(raw, "issue", path),
        fix_pr=_require_int(raw, "fix_pr", path),
        base_sha=_require_text(raw, "base_sha", path),
        fix_sha=_require_text(raw, "fix_sha", path),
        seed_paths=tuple(str(item) for item in seed_paths),
        withheld_files={str(key): str(value) for key, value in withheld.items()},
    )


def _apply_edits(base: Mapping[str, str], edits: object, path: str) -> dict[str, str]:
    """Apply `{path, old, new}` edits to base files; each `old` must occur exactly once."""
    if not isinstance(edits, list) or not edits:
        raise ControlAblationConfigError(f"{path} must be a non-empty array")
    files: dict[str, str] = {}
    for index, edit in enumerate(edits):
        where = f"{path}[{index}]"
        if not isinstance(edit, dict):
            raise ControlAblationConfigError(f"{where}: expected an object")
        _check_keys(edit, frozenset({"path", "old", "new"}), where)
        target = _require_text(edit, "path", where)
        old = _require_text(edit, "old", where)
        new = edit.get("new")
        if not isinstance(new, str):
            raise ControlAblationConfigError(f"{where}.new must be a string")
        current = files.get(target, base.get(target))
        if current is None:
            raise ControlAblationConfigError(f"{where}.path {target!r} is not a seeded file")
        count = current.count(old)
        if count != 1:
            raise ControlAblationConfigError(f"{where}.old occurs {count} times in {target}")
        files[target] = current.replace(old, new)
    return files


def _resolve_control(
    raw: object, path: str, repo_root: Path, source: TaskSource, base: Mapping[str, str]
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ControlAblationConfigError(f"{path}: expected an object")
    _check_keys(raw, _CONTROL_KEYS, path)
    files: dict[str, str] = {}
    from_fix = raw.get("files_from_fix", [])
    if not isinstance(from_fix, list):
        raise ControlAblationConfigError(f"{path}.files_from_fix must be an array")
    for item in from_fix:
        files[str(item)] = read_blob(repo_root, source.fix_sha, str(item))
    if "edits" in raw:
        files.update(_apply_edits(base, raw["edits"], f"{path}.edits"))
    if not files:
        raise ControlAblationConfigError(f"{path} changes no file")
    return {"files": files, "response": raw.get("response")}


def substitute_python(argv: object, python: str) -> object:
    """Replace each `{python}` argv element with the runner's interpreter."""
    if not isinstance(argv, list):
        return argv
    return [python if item == PYTHON_TOKEN else item for item in argv]


def _load_one(raw: object, index: int, repo_root: Path, python: str) -> tuple[Task, TaskSource]:
    path = f"tasks[{index}]"
    if not isinstance(raw, dict):
        raise ControlAblationConfigError(f"{path}: expected an object")
    _check_keys(raw, _TASK_KEYS, path)
    source = _load_source(raw.get("source"), f"{path}.source")
    base = read_tree(repo_root, source.base_sha, source.seed_paths)
    withheld = {
        dest: read_blob(repo_root, source.fix_sha, origin)
        for dest, origin in source.withheld_files.items()
    }
    raw_controls = raw.get("controls")
    if not isinstance(raw_controls, dict):
        raise ControlAblationConfigError(f"{path}.controls: expected an object")
    controls = {
        name: _resolve_control(value, f"{path}.controls.{name}", repo_root, source, base)
        for name, value in raw_controls.items()
    }
    resolved = {
        **{key: value for key, value in raw.items() if key not in ("source", "notes")},
        "setup_files": base,
        "followup_files": withheld,
        "acceptance": substitute_python(raw.get("acceptance"), python),
        "followup": substitute_python(raw.get("followup"), python),
        "controls": controls,
    }
    return load_task(resolved, index, cases=frozenset({CASE})), source


def load_historical_tasks(
    payload: Mapping[str, Any], repo_root: Path, python: str
) -> HistoricalCorpus:
    """Resolve a schema_version 2 document into `Task` values (issue #6814).

    Refuses (`ControlAblationConfigError`) an unknown key, a missing commit or
    path, non-UTF-8 content, a known-bad edit whose `old` text is not unique, a
    duplicate id, and tasks that do not share one base commit (controls are
    read once, from that commit).
    """
    if not is_historical(payload):
        raise ControlAblationConfigError(f"schema_version must be {SCHEMA_VERSION}")
    _check_keys(payload, frozenset({"schema_version", "tasks"}), "task document")
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ControlAblationConfigError("tasks must be a non-empty array")
    tasks: list[Task] = []
    sources: dict[str, TaskSource] = {}
    for index, raw in enumerate(raw_tasks):
        task, source = _load_one(raw, index, repo_root, python)
        if task.id in sources:
            raise ControlAblationConfigError(f"duplicate task id: {task.id!r}")
        tasks.append(task)
        sources[task.id] = source
    base_shas = {source.base_sha for source in sources.values()}
    if len(base_shas) != 1:
        raise ControlAblationConfigError(
            f"every task must share one base_sha so controls read one tree; got {sorted(base_shas)}"
        )
    return HistoricalCorpus(tasks=tasks, sources=sources)


def withheld_markers(sources: Mapping[str, TaskSource], repo_root: Path) -> dict[str, list[str]]:
    """Strings whose appearance in a tool call means the agent reached withheld evidence.

    The hidden check paths, the fix commit (abbreviated too, as `git` prints it),
    the fix PR, and the runner's own checkout, which holds the shipped fix.
    """
    return {
        task_id: [
            *source.withheld_files,
            source.fix_sha[:7],
            f"/pull/{source.fix_pr}",
            str(repo_root),
        ]
        for task_id, source in sources.items()
    }


def load_corpus(
    tasks_file: Path, repo_root: Path, workspace_root: Path, python: str
) -> tuple[dict[str, Any], list[Task], Mapping[str, TaskSource], Path]:
    """Load either schema; return (payload, tasks, historical sources, control root).

    A schema_version 2 file names real commits, so its controls are read from
    the base commit's tree, extracted under `workspace_root`, never from the
    current checkout. A version 1 file reads controls from `repo_root`.
    """
    try:
        payload = json.loads(tasks_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ControlAblationConfigError(f"could not read task file {tasks_file}: {exc}") from exc
    if not isinstance(payload, dict) or not is_historical(payload):
        return payload, load_tasks(payload), {}, repo_root
    corpus = load_historical_tasks(payload, repo_root, python)
    root = workspace_root / f"_base-{corpus.base_sha[:12]}"
    return payload, corpus.tasks, corpus.sources, materialize_tree(repo_root, corpus.base_sha, root)
