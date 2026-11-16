"""Per-PR state and the single-watcher lock for pr_wait.py.

State lives in the user state directory under ``pr-babysit``: one JSON file
and one lock file per PR. The lock is a non-blocking exclusive lock, so a
second watcher for the same PR is refused at once.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

Json = dict[str, Any]

# A state file older than this describes an old session. Start a fresh
# baseline instead of replaying hours of comments as new events.
STALE_STATE_SECONDS = 6 * 3600


@dataclass
class State:
    """What earlier polls already reported for one PR."""

    head: str = ""
    base_oid: str = ""
    merge_state: str = ""
    seen: set[str] = field(default_factory=set)
    thread_counts: dict[str, int] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)
    failing: set[str] = field(default_factory=set)
    green_head: str = ""
    head_seen_at: float = 0.0
    blockers: set[str] = field(default_factory=set)

    def to_json(self) -> Json:
        return {
            "head": self.head,
            "base_oid": self.base_oid,
            "merge_state": self.merge_state,
            "seen": sorted(self.seen),
            "thread_counts": self.thread_counts,
            "totals": self.totals,
            "failing": sorted(self.failing),
            "green_head": self.green_head,
            "head_seen_at": self.head_seen_at,
            "blockers": sorted(self.blockers),
        }

    @classmethod
    def from_json(cls, data: Json) -> State:
        return cls(
            head=str(data.get("head", "")),
            base_oid=str(data.get("base_oid", "")),
            merge_state=str(data.get("merge_state", "")),
            seen=set(data.get("seen", [])),
            thread_counts={str(k): int(v) for k, v in data.get("thread_counts", {}).items()},
            totals={str(k): int(v) for k, v in data.get("totals", {}).items()},
            failing=set(data.get("failing", [])),
            green_head=str(data.get("green_head", "")),
            head_seen_at=float(data.get("head_seen_at", 0.0)),
            blockers=set(data.get("blockers", [])),
        )


def state_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "pr-babysit"


def state_key(owner: str, name: str, number: int) -> str:
    """GitHub names are case-insensitive, so one PR maps to one lock."""
    return f"{owner}__{name}__{number}".lower()


def acquire_lock(path: Path) -> IO[str] | None:
    """Take a non-blocking exclusive lock. Return None when another holds it."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")  # held for the process life; closed on refusal
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def load_state(path: Path, now: float) -> State | None:
    """Return the saved state, or None for a fresh baseline."""
    try:
        if now - path.stat().st_mtime > STALE_STATE_SECONDS:
            return None
        return State.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def save_state(path: Path, state: State) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.to_json()), encoding="utf-8")
    os.replace(tmp, path)
