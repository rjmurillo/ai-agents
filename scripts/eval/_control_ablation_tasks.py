"""Task data model and loader for the reduced-control ablation (REQ-046 AC-1).

Pure, stdlib only. `load_tasks_file` refuses (`ControlAblationConfigError`)
a duplicate id, an unknown or missing case, an empty `allowed_paths`, a
follow-up file that shadows a setup file, a path that escapes the workspace,
and any unknown key. `_control_ablation.py` builds records from the loaded
`Task`; `eval_control_ablation.py` is the CLI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CASES: frozenset[str] = frozenset(
    {
        "ambiguous_requirement",
        "stale_resume",
        "plausible_but_wrong",
        "consequential_hold",
        "hidden_regression",
    }
)


class ControlAblationConfigError(ValueError):
    """A task file, control name, or grade input is invalid (REQ-046 AC-1)."""


# ---------------------------------------------------------------------------
# Task data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResponseCheck:
    kind: str
    pattern: str


@dataclass(frozen=True, slots=True)
class TaskControl:
    """One of a task's `known_good`/`known_bad` dry-run controls."""

    files: Mapping[str, str]
    response: str


@dataclass(frozen=True, slots=True)
class Task:
    """One code change request (REQ-046 ontology)."""

    id: str
    case: str
    prompt: str
    setup_files: Mapping[str, str]
    allowed_paths: tuple[str, ...]
    acceptance: tuple[str, ...]
    followup_files: Mapping[str, str]
    followup: tuple[str, ...]
    external_marker: str | None
    response_checks: tuple[ResponseCheck, ...]
    controls: Mapping[str, TaskControl] = field(repr=False)


# ---------------------------------------------------------------------------
# Task loader (REQ-046 AC-1)
# ---------------------------------------------------------------------------

_TASK_KEYS = frozenset(
    {
        "id",
        "case",
        "prompt",
        "setup_files",
        "allowed_paths",
        "acceptance",
        "followup_files",
        "followup",
        "external_marker",
        "response_checks",
        "controls",
    }
)
_TASK_CONTROL_NAMES = frozenset({"known_good", "known_bad"})


def _require_dict(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControlAblationConfigError(f"{path}: expected an object, got {type(value).__name__}")
    return value


def _require_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ControlAblationConfigError(f"{path}: expected a non-empty string, got {value!r}")
    return value


def _require_relative_path(value: object, path: str) -> str:
    """Require a task-declared path to stay inside the workspace (CWE-22).

    Mirrors `_runtime_parity._relative_path` (read 2026-09-28,
    `scripts/eval/_runtime_parity.py:94-99`): "raw = _string(value, field);
    path = Path(raw); if path.is_absolute() or '..' in path.parts: raise
    ParityConfigError(...)". Same as canonical: absolute paths and any `..`
    segment refuse. Different than canonical: this raises
    `ControlAblationConfigError`, this module's own exception type, since
    DESIGN-044 defines no shared error type with `_runtime_parity`.
    """
    raw = _require_str(value, path)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ControlAblationConfigError(f"{path} must stay inside the task workspace: {raw!r}")
    if ".git" in candidate.parts:
        raise ControlAblationConfigError(f"{path} must not write inside .git: {raw!r}")
    return raw


def _require_str_mapping(value: object, path: str) -> dict[str, str]:
    """Require every key to be a workspace-relative path and every value a string."""
    mapping = _require_dict(value, path)
    for key, item in mapping.items():
        _require_relative_path(key, f"{path} key")
        if not isinstance(item, str):
            raise ControlAblationConfigError(f"{path}[{key!r}] must be a string")
    return mapping


def _require_str_list(value: object, path: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ControlAblationConfigError(f"{path}: expected an array of non-empty strings")
    if not allow_empty and not value:
        raise ControlAblationConfigError(f"{path}: must not be empty")
    return tuple(value)


def _load_response_check(value: object, path: str) -> ResponseCheck:
    raw = _require_dict(value, path)
    unknown = raw.keys() - {"kind", "pattern"}
    if unknown:
        raise ControlAblationConfigError(f"{path}: unknown key(s) {sorted(unknown)}")
    kind = _require_str(raw.get("kind"), f"{path}.kind")
    if kind not in {"regex", "not_regex"}:
        raise ControlAblationConfigError(
            f"{path}.kind must be 'regex' or 'not_regex', got {kind!r}"
        )
    pattern = _require_str(raw.get("pattern"), f"{path}.pattern")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ControlAblationConfigError(f"{path}.pattern is invalid: {exc}") from exc
    return ResponseCheck(kind=kind, pattern=pattern)


def _load_task_control(value: object, path: str) -> TaskControl:
    raw = _require_dict(value, path)
    unknown = raw.keys() - {"files", "response"}
    if unknown:
        raise ControlAblationConfigError(f"{path}: unknown key(s) {sorted(unknown)}")
    return TaskControl(
        files=_require_str_mapping(raw.get("files", {}), f"{path}.files"),
        response=_require_str(raw.get("response"), f"{path}.response"),
    )


def _load_controls(value: object, path: str) -> dict[str, TaskControl]:
    raw = _require_dict(value, path)
    missing = _TASK_CONTROL_NAMES - raw.keys()
    if missing:
        raise ControlAblationConfigError(f"{path}: missing control(s) {sorted(missing)}")
    unknown = raw.keys() - _TASK_CONTROL_NAMES
    if unknown:
        raise ControlAblationConfigError(f"{path}: unknown control(s) {sorted(unknown)}")
    return {
        name: _load_task_control(raw[name], f"{path}.{name}")
        for name in _TASK_CONTROL_NAMES
    }


def _load_task(value: object, index: int) -> Task:
    path = f"tasks[{index}]"
    raw = _require_dict(value, path)
    unknown = raw.keys() - _TASK_KEYS
    if unknown:
        raise ControlAblationConfigError(f"{path}: unknown key(s) {sorted(unknown)}")
    missing = _TASK_KEYS - raw.keys()
    if missing:
        raise ControlAblationConfigError(f"{path}: missing key(s) {sorted(missing)}")
    case = _require_str(raw.get("case"), f"{path}.case")
    if case not in CASES:
        raise ControlAblationConfigError(
            f"{path}.case is unknown: {case!r}; expected one of {sorted(CASES)}"
        )
    external_marker_raw = raw.get("external_marker")
    external_marker = (
        None
        if external_marker_raw is None
        else _require_relative_path(external_marker_raw, f"{path}.external_marker")
    )
    setup_files = _require_str_mapping(raw.get("setup_files", {}), f"{path}.setup_files")
    followup_files = _require_str_mapping(raw.get("followup_files", {}), f"{path}.followup_files")
    overlap = setup_files.keys() & followup_files.keys()
    if overlap:
        raise ControlAblationConfigError(
            f"{path}: followup_files overlaps setup_files at {sorted(overlap)}"
        )
    response_checks_raw = raw.get("response_checks")
    if not isinstance(response_checks_raw, list):
        raise ControlAblationConfigError(f"{path}.response_checks must be an array")
    return Task(
        id=_require_str(raw.get("id"), f"{path}.id"),
        case=case,
        prompt=_require_str(raw.get("prompt"), f"{path}.prompt"),
        setup_files=setup_files,
        allowed_paths=_require_str_list(
            raw.get("allowed_paths"), f"{path}.allowed_paths", allow_empty=False
        ),
        acceptance=_require_str_list(
            raw.get("acceptance"), f"{path}.acceptance", allow_empty=False
        ),
        followup_files=followup_files,
        followup=_require_str_list(
            raw.get("followup"), f"{path}.followup", allow_empty=False
        ),
        external_marker=external_marker,
        response_checks=tuple(
            _load_response_check(item, f"{path}.response_checks[{item_index}]")
            for item_index, item in enumerate(response_checks_raw)
        ),
        controls=_load_controls(raw.get("controls"), f"{path}.controls"),
    )


def load_tasks(payload: Mapping[str, Any]) -> list[Task]:
    """Parse and validate a control-ablation task corpus (REQ-046 AC-1).

    Refuses (`ControlAblationConfigError`) a duplicate id, an unknown case,
    a missing case (every one of the five #5768 cases must appear exactly
    once across the file), an empty `allowed_paths`, a follow-up file that
    is also a setup file, and an unknown key at any level.
    """
    root = _require_dict(payload, "task document")
    if root.get("schema_version") != 1:
        raise ControlAblationConfigError("schema_version must be 1")
    raw_tasks = root.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ControlAblationConfigError("tasks must be a non-empty array")
    unknown_root = root.keys() - {"schema_version", "tasks"}
    if unknown_root:
        raise ControlAblationConfigError(f"task document: unknown key(s) {sorted(unknown_root)}")
    tasks: list[Task] = []
    seen_ids: set[str] = set()
    seen_cases: set[str] = set()
    for index, value in enumerate(raw_tasks):
        task = _load_task(value, index)
        if task.id in seen_ids:
            raise ControlAblationConfigError(f"duplicate task id: {task.id!r}")
        seen_ids.add(task.id)
        if task.case in seen_cases:
            raise ControlAblationConfigError(f"case {task.case!r} appears more than once")
        seen_cases.add(task.case)
        tasks.append(task)
    missing_cases = CASES - seen_cases
    if missing_cases:
        raise ControlAblationConfigError(
            f"task document is missing case(s) {sorted(missing_cases)}"
        )
    return tasks


def load_tasks_file(path: Path) -> list[Task]:
    """Read and parse a task corpus file (REQ-046 AC-1)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ControlAblationConfigError(f"could not read task file {path}: {exc}") from exc
    except ValueError as exc:
        raise ControlAblationConfigError(f"task file {path} is not valid JSON: {exc}") from exc
    return load_tasks(payload)
