"""Rejected-edit buffer and sha256 byte identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from _skillopt_patching import SkillOptError


# --------------------------------------------------------------------------- #
# Rejected-edit buffer: negative-feedback memory (stable-signature dedup)
# --------------------------------------------------------------------------- #
def edit_signature(patches: list[dict[str, Any]]) -> str:
    """Stable sha256 over the normalized patch list. Order- and whitespace-exact.

    Two structurally identical edit batches hash equal regardless of key order,
    so a re-proposed known-bad edit is recognized even if the optimizer reorders
    JSON keys.
    """
    normalized = json.dumps(patches, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_known_bad(buffer_path: Path, patches: list[dict[str, Any]]) -> bool:
    """True if this exact edit batch was already rejected (present in buffer)."""
    sig = edit_signature(patches)
    return any(entry.get("edit_signature") == sig for entry in _read_buffer(buffer_path))


def append_rejected(
    buffer_path: Path,
    patches: list[dict[str, Any]],
    score: float,
    incumbent: float,
    note: str,
    step: int,
) -> None:
    """Append a rejected edit to the JSONL buffer. Idempotent on signature."""
    if is_known_bad(buffer_path, patches):
        return
    entry = {
        "edit_signature": edit_signature(patches),
        "score": score,
        "incumbent": incumbent,
        "failure_note": note,
        "step": step,
        "patches": patches,
    }
    buffer_path.parent.mkdir(parents=True, exist_ok=True)
    with buffer_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _read_buffer(buffer_path: Path) -> list[dict[str, Any]]:
    """Parse the JSONL buffer. A malformed line raises, naming its line number."""
    if not buffer_path.exists():
        return []
    entries = []
    for number, raw in enumerate(buffer_path.read_bytes().decode("utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SkillOptError(
                f"{buffer_path}: line {number} is not valid JSON: {exc.msg}"
            ) from exc
        if not isinstance(entry, dict):
            raise SkillOptError(f"{buffer_path}: line {number} is not a JSON object")
        entries.append(entry)
    return entries


# --------------------------------------------------------------------------- #
# Hashing: byte identity of incumbent, null control, and deployed copy
# --------------------------------------------------------------------------- #
def file_sha256(path: Path | str) -> str:
    """Hex sha256 of the file's exact bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
