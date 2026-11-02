"""The contract between the flaky rerun step and the flaky report step.

``rerun`` and ``report`` run as separate workflow steps, so they share state
through one JSON file in the leg's output directory. This module owns that
file's name, shape, and status values, the exit codes both steps return, and
the JSON writer both use.

EXIT CODES (ADR-035): 0 ok, 1 the first run failed, 2 a state file this
script did not write, 3 a missing or malformed input.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ci._flaky_inputs import InputError

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

STATE_VERSION = 1
STATE_FILE = "rerun-state.json"
RERUN_JUNIT_FILE = "rerun.xml"
RERUN_CACHE_DIR = "rerun-cache"
REPORT_FILE = "flaky-tests.json"

STATUS_RAN = "ran"
STATUS_STARTED = "started"
STATUS_OVER_CAP = "skipped_over_cap"
STATUS_NO_NODEIDS = "skipped_no_nodeids"
KNOWN_STATUSES = frozenset({STATUS_RAN, STATUS_STARTED, STATUS_OVER_CAP, STATUS_NO_NODEIDS})


class StateError(Exception):
    """The state file is not one this script wrote. Maps to exit 2."""


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write *payload* as sorted, indented JSON, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def string_list(state: dict[str, object], key: str) -> list[str]:
    """Return ``state[key]`` when it is a list of strings, else raise StateError."""
    value = state.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise StateError(f"state field {key!r} is not a list of strings")
    return value


def load_state(path: Path) -> dict[str, object] | None:
    """Read the rerun state, or None when the rerun step never wrote it."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"malformed rerun state {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        raise StateError(f"{path}: not a version {STATE_VERSION} rerun state")
    if data.get("status") not in KNOWN_STATUSES:
        raise StateError(f"{path}: unknown status {data.get('status')!r}")
    string_list(data, "first_failures")
    string_list(data, "rerun_failures")
    return data
