#!/usr/bin/env python3
"""Add human-timed correction minutes to live run records after the run (issue #5768).

The live drivers (`eval_durable_live.py`, `eval_control_ablation.py`) write
`economics.human_correction_minutes` as null, because no human is present while
they run, and save each run's change under `changes/<control>/`. A human corrects
and times that change afterwards. This tool joins the timed rows to the records:

    eval_human_minutes_join.py --records OUT/current.jsonl OUT/reduced.jsonl \\
        --minutes minutes.json --output-dir OUT/timed

The minutes file format is in `_human_minutes.py`. Each record is matched on
(config.control, task_id, repeat). Input files are never modified: joined copies
go to `--output-dir` under the same file names. A cell with no row stays null and
classifies `UNVERIFIED`.

Exit codes (AGENTS.md): 0 joined copies written. 2 a bad minutes file, a bad
record, a minutes row that matches no record, or an unsafe output directory.
Nothing is written on exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from _human_minutes import HumanMinutes, HumanMinutesError, load_human_minutes, lookup, unmatched
from _outcome_record import DurableOutcomeError, parse_record

EXIT_OK = 0
EXIT_CONFIG = 2

Cell = tuple[str, str, int]


class JoinError(ValueError):
    """The join cannot proceed; nothing is written."""


def _read_rows(path: Path) -> list[dict[str, object]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise JoinError(f"cannot read {path}: {exc}") from exc
    rows: list[dict[str, object]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JoinError(f"{path}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise JoinError(f"{path}:{number}: expected an object")
        rows.append(row)
    if not rows:
        raise JoinError(f"{path}: no records found")
    return rows


def _cell(row: dict[str, object], where: str) -> Cell:
    try:
        record = parse_record(row)
    except DurableOutcomeError as exc:
        raise JoinError(f"{where}: {exc}") from exc
    return (record.config.control, record.task_id, record.repeat)


def join_files(paths: Sequence[Path], minutes: HumanMinutes, output_dir: Path) -> dict[str, object]:
    """Write joined copies of `paths` into `output_dir`. Raises `JoinError` before any write."""
    out_dir = output_dir.resolve()
    names = [path.name for path in paths]
    if len(set(names)) != len(names):
        raise JoinError(f"records files share a file name, so the copies would collide: {names}")
    if any(path.resolve().parent == out_dir for path in paths):
        raise JoinError(
            "--output-dir holds an input records file; joined copies must not replace it"
        )
    joined: dict[str, list[dict[str, object]]] = {}
    produced: set[Cell] = set()
    timed = 0
    for path in paths:
        rows = _read_rows(path)
        for number, row in enumerate(rows, start=1):
            cell = _cell(row, f"{path}:{number}")
            if cell in produced:
                raise JoinError(f"{path}:{number}: duplicate record for cell {cell}")
            produced.add(cell)
            value = lookup(minutes, *cell)
            if value is not None:
                economics = cast("dict[str, object]", row["economics"])  # shape proved above
                economics["human_correction_minutes"] = value
                parse_record(row)
                timed += 1
        joined[path.name] = rows
    missing = unmatched(minutes, produced)
    if missing:
        raise JoinError(f"minutes rows match no record: {missing}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in joined.items():
        (out_dir / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return {
        "records": len(produced),
        "timed": timed,
        "still_null": len(produced) - timed,
        "output_dir": str(out_dir),
        "files": sorted(joined),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--records", type=Path, nargs="+", required=True, help="records JSONL")
    parser.add_argument("--minutes", type=Path, required=True, help="human minutes JSON file")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = join_files(args.records, load_human_minutes(args.minutes), args.output_dir)
    except (JoinError, HumanMinutesError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(json.dumps(summary, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
