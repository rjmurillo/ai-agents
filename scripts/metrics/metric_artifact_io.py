"""Publish a metric artifact without losing the last valid one (#5639).

A PASS or WARN artifact replaces ``path`` atomically. A BLOCKED or INVALID
artifact never touches ``path``: its payload and findings go to a sibling
``<name>.failed.json``, which names the failure page or record for audit. The
write refuses a symlink target (CWE-59), mirroring
``scripts/metrics/gate_latency_io.py``.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from scripts.metrics.metric_artifact import DEFAULT_MAX_AGE, ValidationResult, validate_artifact


class SymlinkRefusedError(Exception):
    """A destination path resolves to a symlink (CWE-59)."""


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What ``publish_artifact`` did: the validation result and the file written."""

    validation: ValidationResult
    written: Path


def failure_path(path: Path) -> Path:
    """Sibling path that holds the latest rejected run for ``path``."""
    return path.with_name(f"{path.stem}.failed.json")


def _write_atomically(path: Path, document: object) -> None:
    if path.is_symlink():
        raise SymlinkRefusedError(f"refusing to write to symlink target: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def publish_artifact(
    path: Path, payload: object, *, now: datetime, max_age: timedelta = DEFAULT_MAX_AGE
) -> PublishResult:
    """Validate ``payload``, then write it to ``path`` or, if rejected, to the failure file."""
    validation = validate_artifact(payload, now=now, max_age=max_age)
    if validation.reportable:
        _write_atomically(path, payload)
        return PublishResult(validation, path)
    record = {
        "validation": {
            "status": validation.status,
            "findings": [
                {"status": f.status, "field": f.field, "message": f.message}
                for f in validation.findings
            ],
        },
        "payload": payload,
    }
    target = failure_path(path)
    _write_atomically(target, record)
    return PublishResult(validation, target)
