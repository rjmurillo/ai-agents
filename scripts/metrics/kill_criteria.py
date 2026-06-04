#!/usr/bin/env python3
"""Canonical emitter for REQ-008-09 kill-criteria (K1-K4) telemetry.

This is the one place that knows the on-disk shape of a kill-criteria
event. Every K1-K4 emission point (the drift-guard hook, the drift-check
CI job, the vendored-install check, the local-vs-CI verdict comparison)
calls :func:`emit_event` or the CLI here so the JSONL schema lives in a
single module. Duplicating the json-append logic at each site would let
the four writers drift apart (one of the exact failure modes REQ-008
tracks).

Kill criteria (see
``.agents/specs/requirements/REQ-008-review-axes-convergence.md`` Kill
Criteria section, REQ-008-09):

    K1: drift hook false positive (axis edit the maintainer intended that
        the hook blocked). 3+ in 30 days rolls back the convergence design.
    K2: generator-induced regression in CI prompts. 3+ instances.
    K3: vendored install breakage. 1+ downstream installer reports /review
        fails after a project-toolkit plugin update. Hard fail.
    K4: drift between local /review verdict and CI verdict on the same
        commit. 3+ in 30 days.

Event shape (one JSON object per line, append-only)::

    {"schemaVersion": 1, "ts": "<ISO-8601 UTC>", "kind": "K1",
     "detail": "<free text the emission point controls>"}

``schemaVersion`` is included so a future shape change is diagnosable
(see ``.claude/rules/data-intensive-applications.md`` schema evolution).
``ts`` is wall-clock UTC, used only for the 30-day rollover window, not
for causal ordering.

System of record: ``.agents/metrics/drift-events.jsonl`` is the SoR for
kill-criteria counts. The file is append-only; readers tally by ``kind``
within the trailing 30 days. Real telemetry is git-ignored; only an empty
seed (``.gitkeep``) is tracked so the directory exists on a fresh clone.

Detail field: callers pass structured, self-generated strings (drift
paths, counts, commit SHAs), never untrusted external pastes, so the
secret-redaction backstop (``.claude/rules/secret-redaction.md``) does not
run on this hot path. Do not feed user-pasted text into ``detail``.

Idempotency: each call appends exactly one line. The append is guarded by
``hook_utilities.lock_file`` when that lib is importable (the hook
context), and falls back to a plain append otherwise. A single retried
caller will append twice by design; dedupe, if needed, happens at read
time on ``(ts, kind, detail)``.

Exit Codes (ADR-035), CLI only:
    0 = event written
    1 = logic error (unknown kind)
    2 = usage / configuration error (bad arguments)
    3 = external failure (could not write the metrics file)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

KillCriterion = Literal["K1", "K2", "K3", "K4"]

VALID_KINDS: Final[frozenset[str]] = frozenset({"K1", "K2", "K3", "K4"})

SCHEMA_VERSION: Final[int] = 1

# Path of the events file relative to the repository root.
EVENTS_RELPATH: Final[str] = ".agents/metrics/drift-events.jsonl"


def _try_lock_helpers() -> tuple[object | None, object | None]:
    """Return (lock_file, unlock_file) from hook_utilities, or (None, None).

    The drift-guard hook runs with ``hook_utilities`` already on
    ``sys.path`` (the plugin bootstrap put it there). Standalone CLI and
    script callers usually do not. When the helpers are unavailable, the
    caller falls back to a plain append; a missing advisory lock only
    matters when two writers race, which is rare for these low-frequency
    events.
    """
    try:
        from hook_utilities import lock_file, unlock_file  # noqa: PLC0415
    except ImportError:
        return None, None
    return lock_file, unlock_file


def _repo_root() -> Path:
    """Resolve the repository root by walking up to the ``.git`` marker.

    Falls back to the current working directory when no marker is found
    so the emitter never raises purely on path resolution; the write
    itself surfaces any real failure.
    """
    current = Path.cwd().resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return Path.cwd().resolve()
        current = parent


def build_event(kind: KillCriterion, detail: str) -> dict[str, object]:
    """Build a kill-criteria event dict.

    Args:
        kind: One of ``K1``-``K4``.
        detail: Free-text describing the trigger. Caller-controlled,
            not untrusted input.

    Returns:
        The event as a plain dict, ready to serialize.

    Raises:
        ValueError: ``kind`` is not a recognized kill criterion.
    """
    if kind not in VALID_KINDS:
        msg = f"unknown kill criterion {kind!r}; expected one of {sorted(VALID_KINDS)}"
        raise ValueError(msg)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ts": datetime.now(tz=UTC).isoformat(),
        "kind": kind,
        "detail": detail,
    }


def _append_line(path: Path, line: str) -> None:
    """Append a single line to ``path``, creating parents as needed.

    Uses the ``hook_utilities`` advisory lock when available so two
    concurrent writers do not interleave. The lock is best-effort; the
    write proceeds without it when the helpers are absent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file, unlock_file = _try_lock_helpers()
    with path.open("a", encoding="utf-8") as handle:
        if lock_file is not None and unlock_file is not None:
            lock_file(handle)
            try:
                handle.write(line)
            finally:
                unlock_file(handle)
        else:
            handle.write(line)


def emit_event(
    kind: KillCriterion,
    detail: str,
    events_path: Path | None = None,
) -> dict[str, object]:
    """Append one kill-criteria event to the metrics file.

    Args:
        kind: One of ``K1``-``K4``.
        detail: Free-text describing the trigger (caller-controlled).
        events_path: Override for the events file. Defaults to
            ``<repo-root>/.agents/metrics/drift-events.jsonl``. Tests
            pass a temp path here to mock the write boundary.

    Returns:
        The event dict that was written.

    Raises:
        ValueError: ``kind`` is invalid.
        OSError: The metrics file could not be written.
    """
    event = build_event(kind, detail)
    target = events_path if events_path is not None else _repo_root() / EVENTS_RELPATH
    line = json.dumps(event, separators=(",", ":")) + "\n"
    _append_line(target, line)
    return event


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="kill_criteria",
        description="Emit a REQ-008-09 kill-criteria (K1-K4) telemetry event.",
    )
    parser.add_argument(
        "--kind",
        required=True,
        choices=sorted(VALID_KINDS),
        help="Kill criterion to record (K1, K2, K3, or K4).",
    )
    parser.add_argument(
        "--detail",
        required=True,
        help="Free-text description of the trigger (caller-controlled).",
    )
    parser.add_argument(
        "--events-path",
        default=None,
        help="Override for the events JSONL file (default: repo metrics file).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See module docstring for exit codes."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    events_path = Path(args.events_path) if args.events_path else None
    try:
        event = emit_event(args.kind, args.detail, events_path=events_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: could not write metrics file: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(event, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
