"""Full-text corpus export for skill-doctor.

``--export-corpus <path>`` writes one JSON object per user or assistant message,
with no truncation and no head/tail buffer, so another tool can read the whole
text. The seam is the file format, documented in panning-for-gold's
``references/corpus-format.md``. Nothing here imports that skill.

Capture is opt-in. ``SessionState.append`` records full text only while a
``CorpusCapture`` is active, so normal collection output is unchanged.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TextIO

CORPUS_ROLES = frozenset({"user", "assistant"})
SKILL_ROOT = Path(__file__).resolve().parents[1]
REDACTION = "[REDACTED]"
OUTPUT_FILES = frozenset({"inventory.json", "audit_manifest.json"})

# Token shapes that must not reach a corpus file: OpenAI-style keys, GitHub tokens,
# AWS access key ids, JWTs, Slack tokens, and bearer or token auth headers.
SECRET = re.compile(
    r"(?:(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|xox[abps]-[A-Za-z0-9-]{10,}|(?i:bearer\s+|authorization:\s*token\s+)[A-Za-z0-9._~+/=-]{20,})"
)


def redact(text: str) -> str:
    return SECRET.sub(REDACTION, text)


class CorpusCapture:
    """Hold the full-text messages of the session being parsed."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.line: Any = 0

    def begin(self) -> None:
        """Start a new session. Every parser builds one SessionState per session."""
        self.rows = []
        self.line = 0

    def record(self, role: str, text: str, ts: Any) -> None:
        self.record_at(self.line or len(self.rows) + 1, role, text, ts)

    def record_at(self, line: Any, role: str, text: str, ts: Any) -> None:
        if role not in CORPUS_ROLES or not text.strip():
            return
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        self.rows.append({"role": role, "text": text, "ts": ts, "line": line})


_CAPTURE: ContextVar[CorpusCapture | None] = ContextVar("corpus_capture", default=None)


def current_capture() -> CorpusCapture | None:
    return _CAPTURE.get()


class CorpusExporter:
    """Stream redacted corpus rows to one JSONL file."""

    def __init__(self, stream: TextIO, capture: CorpusCapture, target: Path) -> None:
        self._stream, self._capture = stream, capture
        self.target = target
        self.rows_written = 0

    def write_session(self, harness: str, meta: Any, file: str) -> None:
        fallback = meta.get("started_at") or ""
        for row in self._capture.rows:
            record = {
                "source": harness,
                "session": meta.get("id"),
                "path": file,
                "line": row["line"],
                "ts": row["ts"] or fallback,
                "role": row["role"],
                "text": redact(row["text"]),
            }
            self._stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.rows_written += 1


def _refuse(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def _checked_target(raw: str) -> Path:
    target = Path(raw).expanduser().resolve()
    if target.is_relative_to(SKILL_ROOT.resolve()):
        _refuse(f"--export-corpus must not write inside the skill directory: {target}")
    if target.is_dir():
        _refuse(f"--export-corpus needs a file path, got a directory: {target}")
    return target


def refuse_output_collision(raw: str, out: Path) -> None:
    """Refuse an export path that names a file the collector writes under `out`."""
    target = Path(raw).expanduser().resolve()
    root = out.expanduser().resolve()
    if target.parent == root and target.name in OUTPUT_FILES:
        _refuse(f"--export-corpus names a report file under --out: {target}")
    if target.is_relative_to(root / "transcripts"):
        _refuse(f"--export-corpus must not write inside the transcripts directory: {target}")


@contextmanager
def corpus_export(args: Any) -> Iterator[CorpusExporter | None]:
    """Yield an exporter while capture is active, or None when the flag is absent."""
    corpus_only = getattr(args, "harness", "auto") in ("t3", "gemini")
    if not args.export_corpus:
        if corpus_only:
            _refuse(f"--harness {args.harness} needs --export-corpus")
        yield None
        return
    target = _checked_target(args.export_corpus)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        stream = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
    except FileExistsError:
        _refuse(f"--export-corpus refuses to overwrite an existing file: {target}")
    except OSError as exc:
        _refuse(f"cannot write --export-corpus {target}: {exc}")
    capture = CorpusCapture()
    token = _CAPTURE.set(capture)
    try:
        with stream:
            yield CorpusExporter(stream, capture, target)
    except BaseException:
        discard_partial(target)
        raise
    finally:
        _CAPTURE.reset(token)


def discard_partial(target: Path) -> None:
    """Remove a corpus file this run created, so a failed run does not block the next."""
    try:
        target.unlink()
    except OSError:
        pass
