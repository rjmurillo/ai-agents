"""Checkpoint file handling for eval_third_party_gap_replay.py.

A checkpoint is a JSONL file of finished model answers, one row per
(revision, trial). A resumed run reuses those answers, so the rows must be
readable after a kill and must belong to the same experimental arm.
"""

from __future__ import annotations

import hashlib
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

    A killed run can leave a broken last line, with or without a newline.
    ``load_checkpoint`` skips it only while it is last, so an appended row would
    make the next load fail. A broken last line is cut off at its first byte; a
    whole last record without a newline only gets its newline.
    """
    if not path.exists():
        return
    data = path.read_bytes()
    body = data.rstrip(b"\n")
    if not body:
        return
    start = body.rfind(b"\n") + 1
    # Change only the tail in place, so a kill here never loses a finished row.
    try:
        json.loads(body[start:])
    except ValueError:
        with path.open("r+b") as handle:
            handle.truncate(start)
        return
    if not data.endswith(b"\n"):
        with path.open("ab") as handle:
            handle.write(b"\n")


def input_sha256(system: str, user: str) -> str:
    """Identity of the exact prompt one call sends: system prompt, then user prompt."""
    return hashlib.sha256(f"{system}\0{user}".encode()).hexdigest()


def input_mismatch(done: list[dict[str, Any]], expected: dict[tuple[str, int], str]) -> str | None:
    """Why a finished answer was given for a different prompt, or None when all match.

    A ref name can point at new content, and a corpus edit can keep a revision
    id while changing its diff. Only rows this run would reuse are checked.
    """
    for row in done:
        key = (str(row["revision"]), int(row["trial"]))
        if key in expected and row.get("input_sha256") != expected[key]:
            return (
                f"checkpoint row {key[0]} trial {key[1]} answered a different prompt; "
                "use a new checkpoint for changed inputs"
            )
    return None


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
