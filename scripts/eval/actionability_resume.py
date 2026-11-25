"""Resume support for ``predict``: read an existing output and decide which records to keep.

Split out of ``actionability_predict.py``, which re-exports every name here. A rerun on the
same ``--output`` carries over ok records whose provenance and sent text still match, drops a
torn final line, and raises ``OutputError`` for any other damage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.eval.actionability_labels import PROVENANCE_FIELDS, STATUS_OK
from scripts.eval.actionability_message import input_sha256
from scripts.eval.actionability_validate import (
    PREDICTION_CHECKS,
    RecordError,
    finite_number,
    validate_records,
)


class OutputError(Exception):
    """The existing ``--output`` cannot be resumed from. Maps to exit code 2."""


def _decode_lines(path: Path) -> list[str | None]:
    """Split an existing output on newline bytes and decode each line on its own.

    A line that is not valid UTF-8 comes back as None. A crash can tear a multibyte character
    at the tail, and decoding the whole file first would fail the resume on it.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OutputError(f"cannot read {path}: {type(exc).__name__}") from None
    decoded: list[str | None] = []
    for chunk in raw.split(b"\n"):
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            decoded.append(None)
            continue
        if text.strip():
            decoded.append(text)
    return decoded


def _read_prior_records(path: Path) -> list[dict[str, Any]]:
    """Return the records in an existing output. A torn final line is dropped.

    A torn line is one that does not parse, or does not decode as UTF-8, at the end of the file.
    Raises OutputError for any other damage: a bad line before the last, or a line that is not
    a JSON object.
    """
    lines = _decode_lines(path)
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        try:
            if line is None:
                raise json.JSONDecodeError("not UTF-8", "", 0)
            record = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                continue
            raise OutputError(f"line {index + 1} of {path} is not valid JSON") from None
        if not isinstance(record, dict):
            raise OutputError(f"line {index + 1} of {path} is not a JSON object")
        records.append(record)
    return records


def _check_carried(path: Path, index: int, record: dict[str, Any]) -> None:
    """Raise OutputError unless an ok record holds a well-formed verdict.

    Carrying a malformed record forward would put it into the score input unchecked.
    """
    try:
        validate_records([record], PREDICTION_CHECKS, path.name, numbers=[index])
    except RecordError as exc:
        raise OutputError(str(exc)) from None
    if not isinstance(record["is_actionable"], bool) or not finite_number(record["confidence"]):
        raise OutputError(
            f"{path.name} row {index}: an ok record needs a bool is_actionable and a "
            "finite confidence"
        )


def _carried_ok(path: Path, run: dict[str, str]) -> list[dict[str, Any]]:
    """Return the ok records of an existing output, one per id, after checking provenance."""
    carried: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(_read_prior_records(path), start=1):
        if record.get("status") != STATUS_OK:
            continue
        _check_carried(path, index, record)
        record_id = record["id"]
        differing = [f for f in PROVENANCE_FIELDS if record.get(f) != run[f]]
        if differing:
            raise OutputError(
                f"ok records in {path} differ from this run in {', '.join(differing)}; "
                "use a new --output"
            )
        if record_id not in seen:
            seen.add(record_id)
            carried.append(record)
    return carried


def _drop_stale(
    carried: list[dict[str, Any]], selected: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Drop carried records whose row now sends different text, or that record no input hash.

    Only rows in ``selected`` are judged. A record for another split is left alone.
    """
    current = {row["id"]: input_sha256(row) for row in selected}
    kept = [
        r for r in carried if r["id"] not in current or r.get("input_sha256") == current[r["id"]]
    ]
    return kept, len(carried) - len(kept)
