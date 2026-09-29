"""Value objects for the instruction-context byte report (issue #5400)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SizedFile:
    """One file with its UTF-8 byte size and estimated token count."""

    path: str
    size_bytes: int
    estimated_tokens: int


@dataclass(frozen=True)
class ActivatedFile(SizedFile):
    """A file a fixture loads, tagged with why it entered the fixture.

    ``source`` is one of ``always-on``, ``path-scoped-rule``, ``entrypoint``,
    or ``dependency``.
    """

    source: str = ""


def total_bytes(files: Iterable[SizedFile]) -> int:
    return sum(f.size_bytes for f in files)


def total_tokens(files: Iterable[SizedFile]) -> int:
    return sum(f.estimated_tokens for f in files)


def summarize(files: Iterable[SizedFile]) -> dict[str, int]:
    """Return ``files``, ``bytes``, and ``tokens`` totals for one group."""
    listed = list(files)
    return {
        "files": len(listed),
        "bytes": total_bytes(listed),
        "tokens": total_tokens(listed),
    }


def top_contributors(files: Iterable[SizedFile], limit: int) -> list[dict[str, object]]:
    """Return the ``limit`` largest files, ties broken by path for determinism."""
    ranked = sorted(files, key=lambda f: (-f.size_bytes, f.path))[: max(limit, 0)]
    return [{"path": f.path, "bytes": f.size_bytes, "tokens": f.estimated_tokens} for f in ranked]
