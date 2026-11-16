"""Checkpoint file handling for eval_third_party_gap_replay.py.

A checkpoint is a JSONL file of finished model answers, one row per
(revision, trial). A resumed run reuses those answers, so the rows must be
readable after a kill and must belong to the same experimental arm.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The run settings stamped on every row; a resume must match all of them.
STAMP_KEYS = ("prompt_ref", "model", "provider")


def load_checkpoint(path: Path | None) -> list[dict[str, Any]]:
    """Finished rows, one per (revision, trial). Errored rows are dropped so they rerun.

    Two runs that overlapped on one checkpoint can each write the same job. The
    first finished row is kept, so a duplicate never counts a defect twice.
    """
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break  # a killed run can leave a half-written last line
            raise
        if not isinstance(row, dict) or "revision" not in row or "trial" not in row:
            raise ValueError(f"checkpoint {path} holds a line that is not a result row")
        key = (str(row["revision"]), int(row["trial"]))
        if not row.get("error") and key not in seen:
            seen.add(key)
            rows.append(row)
    return rows


def repair_tail(path: Path) -> None:
    """Make the checkpoint safe to append to before a resumed run writes to it.

    A killed run can leave a half-written last line with no newline. Appending
    to it would glue the next answer onto that fragment and lose it. A broken
    fragment is cut off at its first byte; a whole record only gets its newline.
    """
    if not path.exists():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    start = data.rfind(b"\n") + 1
    # Change only the tail in place, so a kill here never loses a finished row.
    try:
        json.loads(data[start:])
    except ValueError:
        with path.open("r+b") as handle:
            handle.truncate(start)
        return
    with path.open("ab") as handle:
        handle.write(b"\n")


def stamp_mismatch(done: list[dict[str, Any]], stamp: dict[str, str]) -> str | None:
    """Why the checkpoint's answers belong to another arm, or None when they match.

    Resuming reuses every finished answer, so one recorded under another prompt
    ref, model, or provider (or under none) would be reported as this arm's.
    """
    for row in done:
        for key in STAMP_KEYS:
            if row.get(key) != stamp[key]:
                return (
                    f"checkpoint row {row['revision']} trial {row['trial']} has "
                    f"{key}={row.get(key)!r}, this run uses {stamp[key]!r}; "
                    "use a new checkpoint for a new arm"
                )
    return None
