#!/usr/bin/env python3
"""Deterministic prefilter for the contradiction lens of panning-for-gold.

Reads a session corpus (JSONL, one message per line, see
references/corpus-format.md) and keeps only the text windows that look like a
measured result contradicting a stated belief. Pure standard library, no model
call. Survivors are written as batch files for an LLM judge.

Tier 1 keeps a window with a strong surprise signal plus a number. Tier 2 keeps
a window with two weaker signals plus a number, or one weaker signal when the
window also names a belief, contrasts it, and compares two numbers. User turns
are mostly prompts and pasted notices, so they need a much higher score than
assistant turns.

EXIT CODES (ADR-035):
    0 - Success
    1 - Logic error (a corpus row fails the contract)
    2 - Config error (missing file, unreadable file, output not writable)
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

LENSES: Final[tuple[str, ...]] = ("contradiction",)
REQUIRED_KEYS: Final[tuple[str, ...]] = ("source", "session", "path", "line", "ts", "role", "text")
KEPT_ROLES: Final[frozenset[str]] = frozenset({"user", "assistant"})

DEFAULT_MAX_BATCH_CHARS: Final[int] = 90_000
MAX_BATCH_ROWS: Final[int] = 90
WINDOW_MAX_CHARS: Final[int] = 1_100
MIN_TEXT_CHARS: Final[int] = 80
MIN_PARAGRAPH_CHARS: Final[int] = 40
TIER1_SCORE: Final[int] = 3
TIER2_SCORE: Final[int] = 2
USER_MIN_SCORE: Final[int] = 7
PRIVATE_FILE_MODE: Final[int] = 0o600

SIG = re.compile(
    r"surpris|contradict|counter-?intuitive|turns out|actually (?:worse|better|hurt|slower|faster|lower|higher)|"
    r"did(?: not|n't) help|no (?:measurable )?(?:lift|improvement|effect|difference|benefit)|ablation|"
    r"wrong about|was wrong|were wrong|assumption (?:was|is) (?:wrong|false)|falsif|refut|backfire|"
    r"worse than|better than expected|opposite of|inverted|regress(?:ed|ion)|\bscored\b|\bbeat\b|"
    r"outperform|underperform|a/?b (?:test|result)|baseline|\bprobe[sd]?\b|measured|empirical|"
    r"stale (?:memory|claim|doc|adr)|memory (?:was|is) (?:wrong|stale)|docs? (?:was|were|is|are) wrong|"
    r"myth|folk|conventional wisdom|common (?:advice|guidance|belief)|expected .{0,40} but (?:got|saw|found)|"
    r"contrary to|despite (?:the )?(?:docs|adr|guidance|advice)|not what (?:the|we) (?:docs|adr|memory)",
    re.I,
)
STRONG = re.compile(
    r"surpris|contradict|counter-?intuitive|turns out|actually (?:worse|better|hurt)|did(?: not|n't) help|"
    r"no (?:measurable )?(?:lift|improvement)|ablation|wrong about|was wrong|falsif|refut|backfire|"
    r"opposite of|inverted|contrary to|conventional wisdom|eureka|memory (?:was|is) (?:wrong|stale)|"
    r"docs? (?:was|were|is|are) wrong",
    re.I,
)
NUM = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|x\b|ms\b|s\b|sec|tokens?|pp\b|/\s*\d+|of \d+)|"
    r"\d+(?:\.\d+)?\s*(?:vs\.?|versus|->|→|to)\s*\d+(?:\.\d+)?|\b\d+\s*/\s*\d+\b",
    re.I,
)
BELIEF = re.compile(
    r"claim|memory|\bADR\b|docs? (?:say|said|state|claim)|expected|assum|predict|hypothes|prior|"
    r"believed|supposed|promis|documented|contradict",
    re.I,
)
CONTRAST = re.compile(
    r"\b(?:but|however|instead|actually|rather than|turned out|yet|whereas|not the|only|never|zero|0 of|none)\b",
    re.I,
)
CMP = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|ms|s|x|tokens?)?\s*(?:vs\.?|versus|->|→|to|from|/|of)\s*\d+(?:\.\d+)?|"
    r"\bfrom \d+.{0,20} to \d+|\b\d+ of \d+\b",
    re.I,
)
# Text a harness injected, not text a person or the agent wrote. Window text that
# matches is dropped before scoring.
INJECTED = re.compile(
    r"<system-reminder>|<task-notification>|<environment_context>|<user_instructions>|"
    r"<command-name>|<local-command-stdout>|<permissions instructions>",
    re.I,
)
# Token shapes redacted again here, so a corpus from any producer is safe to batch.
SECRET = re.compile(
    r"(?:(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|xox[abps]-[A-Za-z0-9-]{10,}|(?i:bearer\s+|authorization:\s*token\s+)[A-Za-z0-9._~+/=-]{20,})"
)


class CorpusError(ValueError):
    """Raised when a corpus row breaks the contract (exit 1)."""


@dataclass
class PrefilterStats:
    """Counts reported in manifest.json."""

    rows_read: int = 0
    rows_skipped_role: int = 0
    windows_injected: int = 0
    windows_scored: int = 0
    windows_dropped_score: int = 0
    windows_duplicate: int = 0
    windows_kept: int = 0
    batches: int = 0
    tiers: dict[str, int] = field(default_factory=lambda: {"1": 0, "2": 0})


def read_corpus(path: Path) -> Iterator[dict[str, Any]]:
    """Yield validated corpus rows. Raises CorpusError, or OSError when unreadable."""
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for number, line in enumerate(stream, start=1):
            if line.strip():
                yield _validated_row(line, number)


def _validated_row(line: str, number: int) -> dict[str, Any]:
    try:
        row = json.loads(line)
    except ValueError as exc:
        raise CorpusError(f"line {number}: not valid JSON ({exc.__class__.__name__})") from exc
    if not isinstance(row, dict):
        raise CorpusError(f"line {number}: row must be a JSON object")
    missing = [key for key in REQUIRED_KEYS if key not in row]
    if missing:
        raise CorpusError(f"line {number}: missing keys {missing}")
    if not isinstance(row["text"], str) or not isinstance(row["role"], str):
        raise CorpusError(f"line {number}: `text` and `role` must be strings")
    return row


def score_window(window: str) -> int:
    """Distinct signal phrases, with distinct strong phrases weighted three times."""
    signals = {m.group(0).lower() for m in SIG.finditer(window)}
    strong = {m.group(0).lower() for m in STRONG.finditer(window)}
    return len(signals) + 3 * len(strong)


def extract_windows(text: str) -> list[str]:
    """Return paragraph windows (one paragraph of context each side) that hold signal and a number."""
    if len(text) < MIN_TEXT_CHARS or not SIG.search(text) or not NUM.search(text):
        return []
    paragraphs = re.split(r"\n\s*\n", text)
    windows: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        if len(paragraph) < MIN_PARAGRAPH_CHARS or not SIG.search(paragraph):
            continue
        before = paragraphs[index - 1] if index > 0 else ""
        after = paragraphs[index + 1] if index + 1 < len(paragraphs) else ""
        window = fit_window(
            SECRET.sub("[REDACTED]", before),
            SECRET.sub("[REDACTED]", paragraph),
            SECRET.sub("[REDACTED]", after),
        )
        if NUM.search(window):
            windows.append(window)
    return windows


def _signal_slice(paragraph: str) -> str:
    """Return at most WINDOW_MAX_CHARS of `paragraph`, centered so a signal and a number survive."""
    if len(paragraph) <= WINDOW_MAX_CHARS:
        return paragraph
    for match in SIG.finditer(paragraph):
        start = max(0, match.start() - WINDOW_MAX_CHARS // 2)
        piece = paragraph[start : start + WINDOW_MAX_CHARS]
        if SIG.search(piece) and NUM.search(piece):
            return piece
    return paragraph[:WINDOW_MAX_CHARS]


def fit_window(before: str, paragraph: str, after: str) -> str:
    """Join context around the signal paragraph and keep that paragraph inside the cap."""
    window = "\n".join(part for part in (before, paragraph, after) if part)
    if len(window) <= WINDOW_MAX_CHARS:
        return window
    core = _signal_slice(paragraph)
    room = WINDOW_MAX_CHARS - len(core)
    lead = before[len(before) - room // 2 :] if room // 2 and before else ""
    tail = after[: max(0, room - len(lead) - 2)] if after else ""
    return "\n".join(part for part in (lead, core, tail) if part)[:WINDOW_MAX_CHARS]


def tier_of(window: str, role: str) -> int | None:
    """Return 1 or 2 when the window survives, else None."""
    score = score_window(window)
    if role == "user":
        return 1 if score >= USER_MIN_SCORE else None
    if score >= TIER1_SCORE:
        return 1
    if score == TIER2_SCORE:
        return 2
    if score == 1 and BELIEF.search(window) and CONTRAST.search(window) and CMP.search(window):
        return 2
    return None


def dedupe_key(window: str) -> str:
    """Hash the whole window. Case and punctuation fold, but a decimal point stays distinct."""
    marked = re.sub(r"(?<=\d)\.(?=\d)", "d", window.lower())
    squeezed = re.sub(r"\W+", "", marked)
    return hashlib.sha256(squeezed.encode("utf-8")).hexdigest()


def _sort_key(row: dict[str, Any]) -> tuple[str, int, str]:
    line = row["line"]
    return (str(row["path"]), line if isinstance(line, int) else 0, str(line))


def select_windows(rows: Iterator[dict[str, Any]], stats: PrefilterStats) -> list[dict[str, Any]]:
    """Window, score, drop injected text, and dedupe by normalized text hash."""
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for row in rows:
        stats.rows_read += 1
        if row["role"] not in KEPT_ROLES:
            stats.rows_skipped_role += 1
            continue
        for window in extract_windows(row["text"]):
            _admit(row, window, seen, kept, stats)
    kept.sort(key=_sort_key)
    return kept


def _admit(
    row: dict[str, Any],
    window: str,
    seen: set[str],
    kept: list[dict[str, Any]],
    stats: PrefilterStats,
) -> None:
    if INJECTED.search(window):
        stats.windows_injected += 1
        return
    stats.windows_scored += 1
    tier = tier_of(window, row["role"])
    if tier is None:
        stats.windows_dropped_score += 1
        return
    key = dedupe_key(window)
    if key in seen:
        stats.windows_duplicate += 1
        return
    seen.add(key)
    kept.append(_output_row(row, window, tier, key))
    stats.tiers[str(tier)] += 1


def _output_row(row: dict[str, Any], window: str, tier: int, key: str) -> dict[str, Any]:
    return {
        "source": row["source"],
        "session": row["session"],
        "path": row["path"],
        "line": row["line"],
        "ts": row["ts"],
        "role": row["role"],
        "tier": tier,
        "score": score_window(window),
        "key": key,
        "text": window,
    }


def make_batches(rows: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    """Split rows in order. A batch closes past `max_chars` of text or MAX_BATCH_ROWS rows."""
    batches: list[list[dict[str, Any]]] = []
    batch: list[dict[str, Any]] = []
    size = 0
    for row in rows:
        batch.append(row)
        size += len(row["text"])
        if size > max_chars or len(batch) >= MAX_BATCH_ROWS:
            batches.append(batch)
            batch, size = [], 0
    if batch:
        batches.append(batch)
    return batches


def batch_name(number: int) -> str:
    return f"batch-{number:03d}.jsonl"


def write_batches(batches: list[list[dict[str, Any]]], out_dir: Path) -> None:
    """Write batch files with ids `<batch>-<index>`, stable for the same corpus and options."""
    for number, batch in enumerate(batches):
        lines = [
            json.dumps({"hid": f"{number:03d}-{index:03d}", **row}, ensure_ascii=False)
            for index, row in enumerate(batch)
        ]
        write_private(out_dir / batch_name(number), "\n".join(lines) + "\n")


def write_private(path: Path, text: str) -> None:
    """Write transcript-derived text readable by the owner only, as the corpus exporter does."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    os.chmod(path, PRIVATE_FILE_MODE)


def output_paths(corpus: Path, out_dir: Path) -> bool:
    """True when `corpus` is a file the run would write under `out_dir`."""
    resolved = corpus.resolve()
    if resolved.parent != out_dir.resolve():
        return False
    return resolved.name == "manifest.json" or fnmatch.fnmatch(resolved.name, "batch-*.jsonl")


def existing_batches(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("batch-*.jsonl")) if out_dir.is_dir() else []


def run_prefilter(corpus: Path, lens: str, out_dir: Path, max_batch_chars: int) -> PrefilterStats:
    """Filter `corpus`, write batches and manifest.json under `out_dir`."""
    if lens not in LENSES:
        raise CorpusError(f"unknown lens {lens!r}")
    if output_paths(corpus, out_dir):
        raise OSError(f"--corpus {corpus} is a file this run would overwrite in {out_dir}")
    stats = PrefilterStats()
    kept = select_windows(read_corpus(corpus), stats)
    batches = make_batches(kept, max_batch_chars)
    stats.windows_kept = len(kept)
    stats.batches = len(batches)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_batches(batches, out_dir)
    manifest = {"lens": lens, "max_batch_chars": max_batch_chars, **stats.__dict__}
    write_private(out_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return stats
