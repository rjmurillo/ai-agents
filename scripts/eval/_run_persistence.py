"""RunPersistence: idempotent JSONL writer for eval-agent-vs-baseline.

DESIGN-004 §5.5, REQ-004 AC-9. Records are appended one per line to
`runs.jsonl` under `evals/security-spike/runs/<RUN_ID>/`. The
`(fixture_id, variant, run_index)` triple is the idempotency key.

Two modes (DESIGN-004 §Failure Modes):
- **Fresh-run**: opening an already-populated `runs.jsonl` raises
  `RunDirectoryNotFreshError`. Any later collision in the loop raises
  `DuplicateRunError`. An unsupported `schemaVersion` raises
  `SchemaVersionError`. A `runs.jsonl` line that does not parse, or
  parses but lacks an identity field, raises
  `MalformedRunRecordError`. The runner maps `DuplicateRunError` to
  exit 1 (logic) and `SchemaVersionError` plus
  `MalformedRunRecordError` to exit 2 (config) per AGENTS.md
  exit-code contract and DESIGN-004 §Failure Modes.
- **Resume**: existing records are loaded; `is_completed(...)` reports
  True only for triples whose prior record was `outcome="success"`.
  Errored triples are retried by default. The writer skips silently
  when the same successful triple is asked to write a second time.

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
    SchemaVersionError,
)


class DuplicateRunError(Exception):
    """Raised when a fresh-run mode write hits an already-recorded triple.

    Maps to runner exit code 1 (logic). The cause is in-process: two
    write attempts at the same `(fixture_id, variant, run_index)`
    triple within one runner invocation. An on-disk format defect
    (corrupt JSON, missing identity field) is a different failure
    class; see `MalformedRunRecordError`.
    """


class MalformedRunRecordError(Exception):
    """Raised when an existing `runs.jsonl` line cannot be parsed back
    into a `RunRecord`.

    Triggers: invalid JSON; a top-level record missing one of the
    identity fields (`fixture_id`, `variant`, `run_index`). Maps to
    runner exit code 2 (config) per DESIGN-004 §Failure Modes; this is
    on-disk corruption, not a logic-class duplicate. Includes the
    JSONL path, the offending line number, and the missing field name
    so an operator can repair the file.
    """


class RunDirectoryNotFreshError(Exception):
    """Raised when fresh-run mode opens a run dir whose `runs.jsonl` is
    already populated. Mixed prompt SHAs and silently skipped triples are
    only safe under explicit `--resume`."""


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
    # AssertionKind is a `str, Enum` mixin (not stdlib StrEnum); asdict
    # leaves it as the enum object on nested dataclasses, which json
    # cannot serialize. Coerce to its string value here.
    for assertion in payload.get("assertions", []):
        kind = assertion.get("kind")
        if hasattr(kind, "value"):
            assertion["kind"] = kind.value
    return json.dumps(payload, sort_keys=True)


def _parse_record(line: str) -> RunRecord | None:
    """Parse one JSONL line back to a RunRecord. Returns None on blank lines.

    Re-hydrates `AssertionResult` from the nested dicts so downstream
    consumers (the report aggregator) can call `.passed` directly.

    Raises `SchemaVersionError` on incompatible `schemaVersion`. A resume
    against an older or newer record set MUST fail fast rather than seed
    the writer with rows that violate the current schema invariants.
    """
    line = line.strip()
    if not line:
        return None
    payload = json.loads(line)
    schema_version = payload.pop("schemaVersion", None)
    if schema_version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"unsupported schemaVersion={schema_version!r} on record "
            f"(supported: {SCHEMA_VERSION})"
        )
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
        # All triples that already exist on disk, regardless of outcome.
        self._seen: set[tuple[str, str, int]] = set()
        # Triples whose prior outcome was `success`. Drives `is_completed`
        # so `--resume` retries errored runs by default.
        self._completed: set[tuple[str, str, int]] = set()
        self._counters = _Counters()
        run_dir.mkdir(parents=True, exist_ok=True)
        if self._jsonl_path.exists():
            self._load_existing_keys()
            # Fresh-run mode against a non-empty run dir is a protocol
            # violation: it would mix prompt SHAs and silently skip prior
            # triples. Resume must be opt-in.
            if not self._resume and self._seen:
                raise RunDirectoryNotFreshError(
                    f"{self._jsonl_path} already contains "
                    f"{len(self._seen)} record(s); refusing to write in "
                    f"fresh-run mode. Pass --resume <RUN_ID> to continue, "
                    f"or choose a new run directory."
                )

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
                    raise MalformedRunRecordError(
                        f"{self._jsonl_path}: line {line_no} is not valid JSON ({exc})"
                    ) from exc
                # Reject incompatible schemas at resume time, before
                # `_seen`/`_completed` get seeded with rows whose shape
                # the writer would otherwise accept.
                schema_version = payload.get("schemaVersion")
                if schema_version != SCHEMA_VERSION:
                    raise SchemaVersionError(
                        f"{self._jsonl_path}: line {line_no} has "
                        f"schemaVersion={schema_version!r} (supported: "
                        f"{SCHEMA_VERSION})"
                    )
                identity_fields = ("fixture_id", "variant", "run_index")
                key = tuple(payload.get(name) for name in identity_fields)
                if None in key:
                    missing = [
                        name
                        for name, value in zip(identity_fields, key)
                        if value is None
                    ]
                    raise MalformedRunRecordError(
                        f"{self._jsonl_path}: line {line_no} missing identity "
                        f"field(s): {', '.join(missing)}"
                    )
                self._seen.add(key)  # type: ignore[arg-type]
                if payload.get("outcome") == "success":
                    self._completed.add(key)  # type: ignore[arg-type]

    def is_completed(self, fixture_id: str, variant: str, run_index: int) -> bool:
        """True only when the prior record was `outcome="success"`.

        Errored triples are NOT considered completed. Under `--resume`,
        callers see them as still-to-run and retry them.
        """
        return (fixture_id, variant, run_index) in self._completed

    def write_record(self, record: RunRecord) -> bool:
        """Append a record. Returns True on write, False on resume-skip.

        Raises `DuplicateRunError` in fresh-run mode if the key already
        exists. Validates `schemaVersion` matches the supported version,
        raising `SchemaVersionError` on mismatch (DESIGN-004 §Failure
        Modes; runner exits with code 2).

        In resume mode, a key whose prior record was `outcome="success"`
        is skipped (returns False). A key whose prior record was
        `outcome="error"` is replaced in place: the errored line is
        removed and the new record is appended.
        """
        if record.schema_version != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"unsupported schemaVersion={record.schema_version} "
                f"(supported: {SCHEMA_VERSION})"
            )
        key = _record_key(record)
        if key in self._seen:
            if self._resume:
                if key in self._completed:
                    self._counters.skipped_resume += 1
                    return False
                # Errored prior record: replace it with the retry.
                self._atomic_replace(key, record)
                if record.outcome == "success":
                    self._completed.add(key)
                self._counters.written += 1
                return True
            raise DuplicateRunError(
                f"duplicate {key} in {self._jsonl_path}; "
                f"each (fixture_id, variant, run_index) must be unique"
            )
        line = _record_to_json_line(record)
        self._atomic_append(line + "\n")
        self._seen.add(key)
        if record.outcome == "success":
            self._completed.add(key)
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

    def _atomic_replace(
        self, key: tuple[str, str, int], record: RunRecord
    ) -> None:
        """Replace any record matching `key` with `record`, atomically.

        Used when `--resume` retries a triple whose prior outcome was
        `error`. Reads the file, drops every line whose identity triple
        matches, appends the new line, then renames over the original.
        """
        new_line = _record_to_json_line(record) + "\n"
        kept: list[str] = []
        if self._jsonl_path.exists():
            with self._jsonl_path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    payload = json.loads(stripped)
                    existing_key = (
                        payload.get("fixture_id"),
                        payload.get("variant"),
                        payload.get("run_index"),
                    )
                    if existing_key == key:
                        continue
                    if not raw_line.endswith("\n"):
                        raw_line += "\n"
                    kept.append(raw_line)

        fd, tmp_path = tempfile.mkstemp(
            prefix=".runs.", suffix=".jsonl.tmp", dir=str(self._run_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                tmp.writelines(kept)
                tmp.write(new_line)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, self._jsonl_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
