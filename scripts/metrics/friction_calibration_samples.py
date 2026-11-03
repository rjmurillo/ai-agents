"""Sensitive sample files for the REQ-048 calibration, redacted before writing.

The samples hold transcript text. They go to a scratch directory outside the
repo, mode 0700 for the directory and 0600 for each file. Every text field
passes through ``scripts.redact_secrets.redact`` first.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypeVar

from scripts.metrics.friction_calibration_scan import (
    DENIAL_SAMPLE_MAX,
    SHELL_SAMPLE_MAX,
    WORD_SAMPLE_MAX,
    Candidates,
)
from scripts.redact_secrets import redact

T = TypeVar("T")
TEXT_CHARS = 200
HEAD_TABLE_SIZE = 60
_REDACT_MARGIN = 400  # redact a longer span than we keep, so a cut token is not left bare


def clip(text: str, limit: int) -> str:
    """Collapse whitespace, redact, then cut to ``limit`` chars.

    Redaction runs before the cut: a token split by the cut would no longer
    match its pattern, so the margin keeps it whole while redacting.
    """
    flat = " ".join(text.split())
    redacted = redact(flat[: limit + _REDACT_MARGIN]).text
    return redacted[:limit]


def merge_keyed(pools: Iterable[list[tuple[float, T]]], limit: int) -> list[T]:
    """The ``limit`` smallest-key items across all pools, in key order."""
    merged = sorted((pair for pool in pools for pair in pool), key=lambda pair: pair[0])
    return [item for _, item in merged[:limit]]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    path.chmod(0o600)


def head_table(heads: Counter[str]) -> list[list[Any]]:
    return [[clip(head, 40), n] for head, n in heads.most_common(HEAD_TABLE_SIZE)]


def write_samples(samples_dir: Path, all_cands: list[Candidates]) -> dict[str, int]:
    """Write both sample files; return row counts."""
    samples_dir.mkdir(parents=True, exist_ok=True)
    samples_dir.chmod(0o700)
    denial = merge_keyed([c.denial.keyed() for c in all_cands], DENIAL_SAMPLE_MAX)
    word = merge_keyed([c.word.keyed() for c in all_cands], WORD_SAMPLE_MAX)
    shell = merge_keyed([c.shell.keyed() for c in all_cands], SHELL_SAMPLE_MAX)
    heads: Counter[str] = Counter()
    for cands in all_cands:
        heads.update(cands.heads)
    denial_rows = [
        {"session_id": sid, "kind": kind, "term": term, "line": clip(line, TEXT_CHARS)}
        for kind, rows in (("marker", denial), ("unmatched_word", word))
        for sid, term, line in rows
    ]
    shell_rows: list[dict[str, Any]] = [{"kind": "head_table", "heads": head_table(heads)}]
    shell_rows += [
        {"kind": "command", "session_id": sid, "command": clip(command, TEXT_CHARS)}
        for sid, command in shell
    ]
    _write_jsonl(samples_dir / "denial_samples.jsonl", denial_rows)
    _write_jsonl(samples_dir / "noncheck_shell_samples.jsonl", shell_rows)
    return {"denial": len(denial), "unmatched_word": len(word), "shell": len(shell)}
