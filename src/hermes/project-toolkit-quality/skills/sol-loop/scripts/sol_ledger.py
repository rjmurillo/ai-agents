"""Run log (ledger) files for sol-loop: read, count rounds, write, and total.

One JSON file per run. The round count for a branch is the number of runs
with status ``ok`` and that branch's key.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

OUTCOMES = ("fixed", "disagree", "declined")


def _counts_valid(counts: object) -> bool:
    """True when ``counts`` maps names to ints (bool excluded) or None."""
    return isinstance(counts, dict) and all(
        v is None or (isinstance(v, int) and not isinstance(v, bool)) for v in counts.values()
    )


def _is_valid_record(record: object) -> bool:
    """True when ``summarize`` can total this record without a TypeError."""
    if not isinstance(record, dict):
        return False
    if any(key in record and not isinstance(record[key], list) for key in ("findings", "dropped")):
        return False
    return "counts" not in record or _counts_valid(record["counts"])


def load_runs(log_dir: Path) -> tuple[list[tuple[Path, dict]], int]:
    """Read every run file in ``log_dir``. Returns (path, record) pairs and the unreadable count.

    A file that is not JSON, not an object, or has a ``findings`` or ``dropped``
    that is not a list, or ``counts`` that is not a map of ints, is unreadable.
    """
    records: list[tuple[Path, dict]] = []
    unreadable = 0
    for path in sorted(log_dir.glob("*.json")) if log_dir.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            record = None
        if _is_valid_record(record):
            records.append((path, record))
        else:
            unreadable += 1
    return records, unreadable


def prior_rounds(log_dir: Path, key: str) -> int:
    """Count completed Sol rounds already logged for this branch."""
    records, _ = load_runs(log_dir)
    return sum(1 for _, r in records if r.get("key") == key and r.get("status") == "ok")


def write_run_log(record: dict, log_dir: Path) -> Path | None:
    """Write one run record as its own new JSON file. Returns None when the write fails."""
    stamp = record["timestamp"].replace(":", "").replace("-", "")
    label = re.sub(r"[^A-Za-z0-9_.-]", "-", record["key"])
    stem = f"{stamp}-{label}-r{record['round']}-{record['status']}"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        for suffix in range(1000):
            target = log_dir / (f"{stem}-{suffix}.json" if suffix else f"{stem}.json")
            try:
                # Mode "x" fails when the file exists, so a racing run or a branch
                # name that maps to the same label never overwrites another log.
                with target.open("x", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
            except FileExistsError:
                continue
            return target
    except OSError as exc:
        print(f"sol_loop: run log not written to {log_dir}: {exc}", file=sys.stderr)
    return None


def replace_run_log(path: Path, record: dict) -> str:
    """Replace an existing run log with ``record`` without ever truncating it first.

    The JSON goes to a sibling temp file, then ``os.replace`` swaps it in, so a
    failed write leaves the original bytes. The original's permission bits are
    kept. Returns "" on success, or the error text after removing the temp file.
    """
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as handle:
            temp = Path(handle.name)
            handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.chmod(temp, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp, path)
    except OSError as exc:
        if temp is not None:
            with contextlib.suppress(OSError):
                temp.unlink()
        return str(exc)
    return ""


def summarize(log_dir: Path) -> dict:
    """Total every run file in ``log_dir``."""
    records, unreadable = load_runs(log_dir)
    runs = [r for _, r in records]
    totals: dict = {"runs": len(runs), "unreadable": unreadable}
    for status in ("ok", "skipped", "unavailable", "escalated"):
        totals[status] = sum(1 for r in runs if r.get("status") == status)
    for key in ("kept", "dropped", "sol_only", "overlap"):
        totals[key] = sum(int((r.get("counts") or {}).get(key) or 0) for r in runs)
    sol_only = [
        f for r in runs for f in r.get("findings", []) if isinstance(f, dict) and f.get("sol_only")
    ]
    totals["sol_only_outcomes"] = {
        outcome: sum(1 for f in sol_only if f.get("outcome", "open") == outcome)
        for outcome in (*OUTCOMES, "open")
    }
    return totals
