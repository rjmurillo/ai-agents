#!/usr/bin/env python3
"""Gold-found synthesis for panning-for-gold.

Combines a final inventory plus per-thread evaluation files into a single
gold-found markdown file with three signal sections (High, Medium, Low).

EXIT CODES (ADR-035):
    0 - Success
    1 - Logic error (missing evaluation, bad inventory)
    2 - Config error (missing file or directory)
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from inventory import Thread  # noqa: E402

SIGNAL_ORDER: tuple[str, ...] = ("high", "medium", "low")
SIGNAL_HEADER: dict[str, str] = {
    "high": "High-Signal",
    "medium": "Medium-Signal",
    "low": "Low-Signal",
}


class SynthesisError(ValueError):
    """Raised when synthesis cannot complete."""


SLUG_MAX_LEN: int = 64
_HASH_LEN: int = 8


def _slugify(title: str) -> str:
    """Convert a thread title into a filesystem-safe slug.

    The slug is truncated to SLUG_MAX_LEN characters to stay below typical
    filesystem name limits (255 bytes). Trailing dashes from truncation are
    stripped so the slug never ends in a separator.
    """
    keep = []
    for ch in title.lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in (" ", "-", "_"):
            keep.append("-")
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:SLUG_MAX_LEN].rstrip("-") or "thread"


def evaluation_filename(thread: Thread) -> str:
    """Return the conventional evaluation filename for a thread.

    Filenames are stable across merge renumbering and collision-resistant.
    The slug is derived from the title (so it survives merges) and a short
    SHA-256 digest of `thread.key` is appended so distinct titles that
    slugify to the same string (e.g. "C" vs "C++") get distinct files.
    """
    base = _slugify(thread.title)
    digest = hashlib.sha256(thread.key.encode("utf-8")).hexdigest()[:_HASH_LEN]
    safe_base = base[: SLUG_MAX_LEN - _HASH_LEN - 1].rstrip("-") or "thread"
    return f"{safe_base}-{digest}.md"


def load_evaluation(thread: Thread, evaluations_dir: Path) -> str:
    """Load the evaluation text for a thread.

    Raises SynthesisError if the evaluation file is missing.
    """
    target = evaluations_dir / evaluation_filename(thread)
    if not target.exists():
        raise SynthesisError(
            f"Missing evaluation for thread {thread.number} ({thread.title!r}): {target}"
        )
    return target.read_text(encoding="utf-8").strip()


def build_gold_found(
    threads: list[Thread],
    evaluations_dir: Path,
    source: str,
    today: date | None = None,
) -> str:
    """Assemble the gold-found markdown text.

    Sections appear in fixed order: High-Signal, Medium-Signal, Low-Signal.
    The metadata block is the first content after the title.
    """
    if today is None:
        today = date.today()

    grouped: dict[str, list[Thread]] = {sig: [] for sig in SIGNAL_ORDER}
    for t in threads:
        grouped.setdefault(t.signal, []).append(t)

    out: list[str] = [
        "# Gold Found",
        "",
        f"- **Source**: {source}",
        f"- **Generated**: {today.isoformat()}",
        f"- **Threads**: {len(threads)}",
        "",
        "---",
        "",
    ]

    for signal in SIGNAL_ORDER:
        out.append(f"## {SIGNAL_HEADER[signal]}")
        out.append("")
        section_threads = grouped.get(signal, [])
        if not section_threads:
            out.append("_None._")
            out.append("")
            continue
        for t in section_threads:
            evaluation = load_evaluation(t, evaluations_dir)
            out.append(f"### Thread {t.number}: {t.title}")
            out.append("")
            for line in t.quote.splitlines() or [""]:
                out.append(f"> {line}")
            out.append("")
            out.append(evaluation)
            out.append("")

    return "\n".join(out).rstrip() + "\n"
