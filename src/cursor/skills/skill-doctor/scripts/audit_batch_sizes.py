"""Transcript sizes for byte-capped review batches.

python3, stdlib only.

The collector writes each transcript to ``<out>/transcripts/<name>`` beside
``<out>/inventory.json``, but stores ``transcript_path`` as ``--out`` was typed. A
relative ``--out`` therefore names a place only the collector's working directory
knows, so the lookup tries the inventory's own ``transcripts`` folder first.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

TRANSCRIPTS_DIR = "transcripts"


def _stat_transcript(path: Any, base_dir: Path | None) -> int | None:
    """Byte size of one transcript, or None when no candidate location is readable."""
    if not path:
        return None
    try:
        candidates = [Path(path)]
        if base_dir is not None:
            candidates.insert(0, base_dir / TRANSCRIPTS_DIR / candidates[0].name)
    except (TypeError, ValueError):
        return None
    for candidate in candidates:
        try:
            return candidate.stat().st_size
        except (OSError, ValueError):
            continue
    return None


def transcript_bytes(
    inventory: Mapping[str, Any],
    key_of: Callable[[Mapping[str, Any]], str],
    base_dir: Path | None = None,
) -> tuple[dict[str, int], list[str]]:
    """Size of each sampled transcript, plus the keys whose transcript could not be read.

    An unreadable transcript counts as 0 bytes, so the caller must report the returned keys.
    """
    sizes: dict[str, int] = {}
    unreadable: list[str] = []
    for session in inventory.get("sessions") or []:
        if not session.get("sampled"):
            continue
        key = key_of(session)
        size = _stat_transcript(session.get("transcript_path"), base_dir)
        if size is None:
            unreadable.append(key)
        sizes[key] = size or 0
    return sizes, sorted(unreadable)
