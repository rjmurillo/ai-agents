"""Durable, append-only audit log shared by every tool that removes a worktree.

Issue #4790: an untracked file vanished during autofix work and no removal
record survived the process that ran, so a later session had nothing to check
it against. Any tool that can delete a persistent worktree, and with it the
untracked files inside, appends one JSON line here before it exits.

The log lives under the main worktree, never under the checkout the tool runs
from: ``git worktree remove`` deletes a linked worktree's gitignored files
too, so a log kept there would be erased by the next removal of that worktree.

Each record carries ``schemaVersion``, ``ts``, ``tool`` (the writer), and
``path``. Writers add their own fields. Readers scan forward and filter on
``tool``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_AUDIT_LOG_RELATIVE = Path(".project-toolkit") / "metrics" / "gc-worktree-removals.jsonl"


def audit_log_path_for(main_worktree: str) -> Path:
    """The durable removal log for the repository whose main worktree is given."""
    return Path(main_worktree) / _AUDIT_LOG_RELATIVE


def append_record(tool: str, path: str, fields: dict[str, Any], *, log_path: Path) -> None:
    """Append one durable audit record for a worktree ``tool`` removed.

    Append-only and never rewritten: readers scan forward, so a later
    session can trust that a line present today stays present tomorrow.
    The parent directory is created if missing so a fresh clone that has
    not yet run a removal does not fail the first one on a missing directory.

    Each line is flushed and fsynced before returning. The removal it records
    has already happened on disk, so a record left in the OS buffer could be
    lost to a crash or power cut while the removal survives. Removals are rare,
    so one fsync per removal costs nothing a reader would notice.
    """
    record = {
        **fields,
        "schemaVersion": SCHEMA_VERSION,
        "ts": datetime.now(UTC).isoformat(),
        "tool": tool,
        "path": path,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
