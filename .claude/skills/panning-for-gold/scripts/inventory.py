#!/usr/bin/env python3
"""Inventory parsing and merging for panning-for-gold.

A thread block has this shape:

    ## Thread N: <title>

    - **Signal**: high | medium | low
    - **Quote**: "<verbatim>"
    - **Context**: <one sentence>
    - **Initial take**: <one sentence>

EXIT CODES (ADR-035):
    0 - Success
    1 - Logic error (malformed inventory)
    2 - Config error (missing file)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "Signal",
    "Quote",
    "Context",
    "Initial take",
)

VALID_SIGNALS: Final[frozenset[str]] = frozenset({"high", "medium", "low"})

_THREAD_HEADER_RE = re.compile(r"^##\s+Thread\s+(\d+):\s*(.+?)\s*$")
_FIELD_RE = re.compile(r"^-\s+\*\*([^*]+)\*\*:\s*(.*)$")


@dataclass(frozen=True)
class Thread:
    """A single thread parsed from an inventory."""

    number: int
    title: str
    signal: str
    quote: str
    context: str
    initial_take: str

    @property
    def key(self) -> str:
        """Deduplication key. Title (lowercased, whitespace-normalized)."""
        return " ".join(self.title.lower().split())


class InventoryError(ValueError):
    """Raised when an inventory cannot be parsed or fails validation."""


class MissingInventoryError(InventoryError):
    """Raised when an inventory file does not exist (config error, exit 2)."""


def normalize_lines(content: str) -> list[str]:
    """Normalize line endings and split into lines."""
    return content.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def parse_inventory(content: str) -> list[Thread]:
    """Parse an inventory markdown string into Thread objects.

    Raises InventoryError if a thread block is malformed.
    """
    if not content.strip():
        return []

    lines = normalize_lines(content)
    threads: list[Thread] = []
    current_header: tuple[int, str] | None = None
    current_fields: dict[str, str] = {}
    current_field_name: str | None = None

    def flush() -> None:
        if current_header is None:
            return
        missing = [f for f in REQUIRED_FIELDS if f not in current_fields]
        if missing:
            raise InventoryError(
                f"Thread {current_header[0]} ({current_header[1]!r}) missing fields: {missing}"
            )
        signal = current_fields["Signal"].strip().lower()
        if signal not in VALID_SIGNALS:
            raise InventoryError(
                f"Thread {current_header[0]} ({current_header[1]!r}) has invalid Signal: {signal!r}"
            )
        quote_value = current_fields["Quote"].strip()
        if (
            len(quote_value) >= 2
            and quote_value.startswith('"')
            and quote_value.endswith('"')
        ):
            quote_value = quote_value[1:-1]
        threads.append(
            Thread(
                number=current_header[0],
                title=current_header[1],
                signal=signal,
                quote=quote_value,
                context=current_fields["Context"].strip(),
                initial_take=current_fields["Initial take"].strip(),
            )
        )

    for raw_line in lines:
        line = raw_line.rstrip()
        header = _THREAD_HEADER_RE.match(line)
        if header is not None:
            flush()
            current_header = (int(header.group(1)), header.group(2).strip())
            current_fields = {}
            current_field_name = None
            continue
        if current_header is None:
            continue
        field = _FIELD_RE.match(line)
        if field is not None:
            name = field.group(1).strip()
            value = field.group(2).strip()
            if name in REQUIRED_FIELDS:
                current_fields[name] = value
                current_field_name = name
            else:
                current_field_name = None
            continue
        if not line.strip():
            current_field_name = None
            continue
        if current_field_name is not None:
            existing = current_fields.get(current_field_name, "")
            current_fields[current_field_name] = (
                existing + "\n" + line.strip() if existing else line.strip()
            )

    flush()
    return threads


def read_inventory(path: Path) -> list[Thread]:
    """Read and parse an inventory file.

    Raises MissingInventoryError if the file does not exist (config error).
    Raises InventoryError on malformed content (logic error).
    """
    if not path.exists():
        raise MissingInventoryError(f"Inventory not found: {path}")
    return parse_inventory(path.read_text(encoding="utf-8"))


def merge(pass1: list[Thread], final: list[Thread]) -> list[Thread]:
    """Merge pass1 and final inventories.

    Threads in `final` take precedence. Pass1 threads not present in final
    (by title key) are appended. Numbering is reassigned starting at 1.
    """
    seen: dict[str, Thread] = {}
    ordered_keys: list[str] = []
    for t in final:
        if t.key not in seen:
            ordered_keys.append(t.key)
        seen[t.key] = t
    for t in pass1:
        if t.key not in seen:
            ordered_keys.append(t.key)
            seen[t.key] = t
    merged: list[Thread] = []
    for n, key in enumerate(ordered_keys, start=1):
        original = seen[key]
        merged.append(
            Thread(
                number=n,
                title=original.title,
                signal=original.signal,
                quote=original.quote,
                context=original.context,
                initial_take=original.initial_take,
            )
        )
    return merged


def render_inventory(threads: list[Thread], source: str = "merged") -> str:
    """Render threads back to markdown inventory format."""
    out: list[str] = [
        "# Thread Inventory",
        "",
        f"Source: {source}",
        "Pass: final",
        "",
        "---",
        "",
    ]
    for t in threads:
        out.extend(
            [
                f"## Thread {t.number}: {t.title}",
                "",
                f"- **Signal**: {t.signal}",
                f'- **Quote**: "{t.quote}"',
                f"- **Context**: {t.context}",
                f"- **Initial take**: {t.initial_take}",
                "",
            ]
        )
    return "\n".join(out).rstrip() + "\n"
