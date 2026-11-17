"""Run log (ledger) files for sol-loop: read, count rounds, write, and total.

One JSON file per run. The round count for a branch is the number of runs
with status ``ok`` and that branch's key.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUTCOMES = ("fixed", "disagree", "declined")


def load_runs(log_dir: Path) -> tuple[list[tuple[Path, dict]], int]:
    """Read every run file in ``log_dir``. Returns (path, record) pairs and the unreadable count."""
    records: list[tuple[Path, dict]] = []
    unreadable = 0
    for path in sorted(log_dir.glob("*.json")) if log_dir.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            record = None
        if isinstance(record, dict):
            records.append((path, record))
        else:
            unreadable += 1
    return records, unreadable


def prior_rounds(log_dir: Path, key: str) -> int:
    """Count completed Sol rounds already logged for this branch."""
    records, _ = load_runs(log_dir)
    return sum(1 for _, r in records if r.get("key") == key and r.get("status") == "ok")


def write_run_log(record: dict, log_dir: Path) -> Path | None:
    """Write one run record as its own JSON file. Returns None when the write fails."""
    stamp = record["timestamp"].replace(":", "").replace("-", "")
    label = re.sub(r"[^A-Za-z0-9_.-]", "-", record["key"])
    stem = f"{stamp}-{label}-r{record['round']}-{record['status']}"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        for suffix in range(1000):
            target = log_dir / (f"{stem}-{suffix}.json" if suffix else f"{stem}.json")
            if not target.exists():
                target.write_text(
                    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                return target
    except OSError as exc:
        print(f"sol_loop: run log not written to {log_dir}: {exc}", file=sys.stderr)
    return None


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
