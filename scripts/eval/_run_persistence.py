"""RunPersistence: idempotent JSONL writer for eval-agent-vs-baseline.

DESIGN-004 §5.5, REQ-004 AC-9. Records are appended one per line to
`runs.jsonl` under `evals/security-spike/runs/<RUN_ID>/`. The
`(fixture_id, variant, run_index)` triple is the idempotency key.

Two modes (DESIGN-004 §Failure Modes):
- **Fresh-run**: collision raises `DuplicateRunError`; the runner exits 1.
- **Resume**: collision means "already done"; the writer skips silently.
  Caller asks `is_completed(...)` before issuing the API call.

Atomic write: each append happens via write-temp-then-rename of the
JSONL file (small, append-only) to avoid partial lines when the process
is interrupted between bytes.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from _eval_agent_types import (
    AssertionKind,
    AssertionResult,
    RunRecord,
    SCHEMA_VERSION,
)


class DuplicateRunError(Exception):
    """Raised when a fresh-run mode write hits an already-recorded triple."""


# Public to make the format obvious at the call site and to give tests a
# stable name to reference.
RUNS_FILENAME = "runs.jsonl"


def _record_key(record: RunRecord) -> tuple[str, str, int]:
    return (record.fixture_id, record.variant, record.run_index)


def _record_to_json_line(record: RunRecord) -> str:
    """Serialize a RunRecord to one JSON line. `assertions` is a list of
    AssertionResult dataclasses; flatten via `asdict` so the JSON shape
    matches DESIGN-004 §5.5 verbatim. `schemaVersion` is renamed from the
    internal `schema_version` attribute on serialization."""
    payload: dict[str, Any] = asdict(record)
    payload["schemaVersion"] = payload.pop("schema_version")
    # AssertionKind is a StrEnum; asdict leaves it as the enum object on
    # nested dataclasses, which json cannot serialize. Coerce here.
    for assertion in payload.get("assertions", []):
        kind = assertion.get("kind")
        if hasattr(kind, "value"):
            assertion["kind"] = kind.value
    return json.dumps(payload, sort_keys=True)


def _parse_record(line: str) -> RunRecord | None:
    """Parse one JSONL line back to a RunRecord. Returns None on blank lines.

    Re-hydrates `AssertionResult` from the nested dicts so downstream
    consumers (the report aggregator) can call `.passed` directly.
    """
    line = line.strip()
    if not line:
        return None
    payload = json.loads(line)
    schema_version = payload.pop("schemaVersion", None)
    payload["schema_version"] = schema_version
    raw_assertions = payload.get("assertions", []) or []
    payload["assertions"] = [
        AssertionResult(
            kind=AssertionKind(a["kind"]),
            pattern=a.get("pattern"),
            expected_value=a.get("expected_value"),
            passed=bool(a.get("passed")),
            extracted=a.get("extracted"),
        )
        for a in raw_assertions
    ]
    return RunRecord(**payload)


@dataclasses.dataclass
class _Counters:
    written: int = 0
    skipped_resume: int = 0


class RunPersistence:
    """JSONL writer with idempotency guard. DESIGN-004 §5.5."""

    def __init__(self, run_dir: Path, *, resume: bool = False) -> None:
        self._run_dir = run_dir
        self._resume = resume
        self._jsonl_path = run_dir / RUNS_FILENAME
        self._seen: set[tuple[str, str, int]] = set()
        self._counters = _Counters()
        run_dir.mkdir(parents=True, exist_ok=True)
        if self._jsonl_path.exists():
            self._load_existing_keys()

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    @property
    def jsonl_path(self) -> Path:
        return self._jsonl_path

    @property
    def resume_mode(self) -> bool:
        return self._resume

    def _load_existing_keys(self) -> None:
        with self._jsonl_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise DuplicateRunError(
                        f"{self._jsonl_path}: line {line_no} is not valid JSON ({exc})"
                    ) from exc
                key = (
                    payload.get("fixture_id"),
                    payload.get("variant"),
                    payload.get("run_index"),
                )
                if None in key:
                    raise DuplicateRunError(
                        f"{self._jsonl_path}: line {line_no} missing identity field"
                    )
                self._seen.add(key)  # type: ignore[arg-type]

    def is_completed(self, fixture_id: str, variant: str, run_index: int) -> bool:
        return (fixture_id, variant, run_index) in self._seen

    def write_record(self, record: RunRecord) -> bool:
        """Append a record. Returns True on write, False on resume-skip.

        Raises `DuplicateRunError` in fresh-run mode if the key already
        exists. Validates `schemaVersion` matches the supported version.
        """
        if record.schema_version != SCHEMA_VERSION:
            raise DuplicateRunError(
                f"unsupported schemaVersion={record.schema_version} "
                f"(supported: {SCHEMA_VERSION})"
            )
        key = _record_key(record)
        if key in self._seen:
            if self._resume:
                self._counters.skipped_resume += 1
                return False
            raise DuplicateRunError(
                f"duplicate {key} in {self._jsonl_path}; "
                f"each (fixture_id, variant, run_index) must be unique"
            )
        line = _record_to_json_line(record)
        self._atomic_append(line + "\n")
        self._seen.add(key)
        self._counters.written += 1
        return True

    def written_count(self) -> int:
        return self._counters.written

    def skipped_count(self) -> int:
        return self._counters.skipped_resume

    def iter_records(self) -> Iterable[RunRecord]:
        if not self._jsonl_path.exists():
            return
        with self._jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                record = _parse_record(line)
                if record is not None:
                    yield record

    def _atomic_append(self, payload: str) -> None:
        """Append with write-temp-then-rename.

        Reads the existing file (if any), writes existing+new to a sibling
        temp file, then renames over the original. Avoids torn writes if
        the process is killed between syscalls.
        """
        existing = (
            self._jsonl_path.read_text(encoding="utf-8")
            if self._jsonl_path.exists()
            else ""
        )
        # NamedTemporaryFile in the same directory ensures rename is atomic
        # (same filesystem). delete=False because we rename it ourselves.
        fd, tmp_path = tempfile.mkstemp(
            prefix=".runs.", suffix=".jsonl.tmp", dir=str(self._run_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                tmp.write(existing)
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, self._jsonl_path)
        except Exception:
            # Best-effort cleanup; do not mask the original error.
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
