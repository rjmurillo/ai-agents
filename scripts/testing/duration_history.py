"""Rolling history of test duration snapshots, stored as one JSON file.

CI keeps the file in the Actions cache and writes it only from pushes to main.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.testing.duration_snapshot import Snapshot

SCHEMA_VERSION = 1


def load_history(path: Path | None) -> tuple[list[Snapshot], str | None]:
    """Read the history file, returning its snapshots and any problem found.

    A missing file is an empty history: the first main run has no
    predecessor, and the cache evicts entries unused for 7 days. A malformed
    file is also treated as empty, with the problem returned so the report
    says so, because the next main run rewrites it. Refusing to run would
    leave a corrupt cache entry in place forever.
    """
    if path is None or not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA_VERSION:
            return [], f"history schema {data.get('schema')!r} is not {SCHEMA_VERSION}"
        return [Snapshot.from_dict(s) for s in data["snapshots"]], None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [], f"history unreadable, starting fresh: {exc}"


def write_history(path: Path, history: list[Snapshot], max_entries: int) -> None:
    """Write the newest ``max_entries`` snapshots, creating the directory."""
    kept = history[-max_entries:]
    payload = {"schema": SCHEMA_VERSION, "snapshots": [s.to_dict() for s in kept]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def write_snapshot(path: Path, snapshot: Snapshot) -> None:
    """Write one snapshot as JSON, creating the directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")
