"""Human-timed correction minutes for live eval runs (issue #5768, REQ-042 and REQ-046).

The live drivers write `economics.human_correction_minutes` as `None`, because
an unattended run has no human and `0.0` would claim a clean correction pass
nobody timed. A record with `None` classifies `UNVERIFIED`. This module is the
input path for a timed pass: a JSON file of rows, one per run cell.

    [
      {"control": "reduced", "task_id": "refactor-1", "repeat": 0, "minutes": 4.5},
      {"control": "current", "task_id": "refactor-1", "repeat": 0, "minutes": 0}
    ]

`minutes` is wall minutes a human spent correcting that run. `0` is a valid
timed value ("a human looked and changed nothing"). A cell with no row stays
`None`. Parsing is strict: an unknown key, a duplicate cell, a negative or
non-finite number, or a boolean raises `HumanMinutesError`.
"""

from __future__ import annotations

import json
import math
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

#: (control, task_id, repeat) -> timed human correction minutes.
HumanMinutes = Mapping[tuple[str, str, int], float]

_ROW_KEYS = frozenset({"control", "task_id", "repeat", "minutes"})


class HumanMinutesError(ValueError):
    """The human-minutes file is unreadable or malformed."""


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HumanMinutesError(f"{where}: minutes must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise HumanMinutesError(f"{where}: minutes must be a finite number >= 0, got {value!r}")
    return number


def _text(value: object, field: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanMinutesError(f"{where}: {field} must be a non-empty string, got {value!r}")
    return value


def _repeat(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HumanMinutesError(f"{where}: repeat must be an integer >= 0, got {value!r}")
    return value


def parse_human_minutes(
    raw: object, *, known_controls: Collection[str] | None = None
) -> dict[tuple[str, str, int], float]:
    """Parse the decoded JSON rows into a cell-keyed mapping, or raise `HumanMinutesError`."""
    if not isinstance(raw, list) or not raw:
        raise HumanMinutesError("expected a non-empty JSON array of rows")
    cells: dict[tuple[str, str, int], float] = {}
    for index, row in enumerate(raw):
        where = f"row {index}"
        if not isinstance(row, dict):
            raise HumanMinutesError(f"{where}: expected an object, got {type(row).__name__}")
        if set(row) != _ROW_KEYS:
            missing = sorted(_ROW_KEYS - set(row))
            extra = sorted(set(row) - _ROW_KEYS)
            raise HumanMinutesError(f"{where}: missing keys {missing}, unknown keys {extra}")
        control = _text(row["control"], "control", where)
        if known_controls is not None and control not in known_controls:
            raise HumanMinutesError(
                f"{where}: control {control!r} is not one of {sorted(known_controls)}"
            )
        key = (control, _text(row["task_id"], "task_id", where), _repeat(row["repeat"], where))
        if key in cells:
            raise HumanMinutesError(f"{where}: duplicate cell {key}")
        cells[key] = _number(row["minutes"], where)
    return cells


def load_human_minutes(
    path: Path, *, known_controls: Collection[str] | None = None
) -> dict[tuple[str, str, int], float]:
    """Read and parse a human-minutes file. Raises `HumanMinutesError` on any problem."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HumanMinutesError(f"cannot read {path}: {exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HumanMinutesError(f"{path} is not valid JSON: {exc}") from exc
    return parse_human_minutes(raw, known_controls=known_controls)


def lookup(minutes: HumanMinutes | None, control: str, task_id: str, repeat: int) -> float | None:
    """The timed value for one cell, or `None` (missing evidence) when none was supplied."""
    if minutes is None:
        return None
    return minutes.get((control, task_id, repeat))


def unmatched(
    minutes: HumanMinutes | None, produced: Collection[tuple[str, str, int]]
) -> list[list[object]]:
    """Supplied cells that matched no produced record, sorted, as `[control, task_id, repeat]`."""
    if not minutes:
        return []
    return [list(key) for key in sorted(set(minutes) - set(produced))]


def unmatched_runs(
    minutes: HumanMinutes | None, runs: Sequence[Mapping[str, object]]
) -> list[list[object]]:
    """`unmatched` over run entries that carry `control`, `task_id`, `repeat`, and a `record`."""
    produced = {
        (str(run["control"]), str(run["task_id"]), int(str(run["repeat"])))
        for run in runs
        if "record" in run
    }
    return unmatched(minutes, produced)
