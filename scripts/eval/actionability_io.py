"""Atomic writes and JSONL reads for the comment actionability eval tools.

Writes to a temporary file in the target directory, then swaps it in with
``os.replace``. A crash before the swap leaves the previous output whole. Same
write-temp-then-replace pattern as ``_report_writer._atomic_write``; kept separate
because that module imports heavy siblings and is private.

The temporary file is created by ``tempfile.mkstemp``, so the published file has
mode 0600.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def split_jsonl_lines(text: str) -> list[str]:
    """Split JSONL text on newline only and drop blank lines.

    Not ``str.splitlines()``: that also breaks on U+2028, U+2029, and U+0085. Those reach
    the file raw because ``write_jsonl`` keeps ``ensure_ascii=False``, so a comment body
    holding one would be cut in half on reload.
    """
    return [line for line in text.split("\n") if line.strip()]


def load_jsonl(path: Path) -> list[dict[str, Any]] | None:
    """Return the JSON objects in ``path``, one per line, or None after logging why not."""
    try:
        lines = split_jsonl_lines(path.read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in lines]
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return None
    if not all(isinstance(row, dict) for row in rows):
        logger.error("%s must hold one JSON object per line", path)
        return None
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write_text(path, text)


def utc_now_iso() -> str:
    """Return the current UTC time to the second. Patched in tests so output stays byte-stable."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def head_sha() -> str:
    """Return this checkout's HEAD commit, or "unknown" when git cannot answer."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"
