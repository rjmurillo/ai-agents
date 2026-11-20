#!/usr/bin/env python3
"""Bare ``:N`` continuations and moved-line clusters for citation freshness.

Extracted from ``citation_anchors.py`` at the file-size ceiling. A bare
colon range binds to the preceding filename when that basename is unique.
A cited block that was already stale can still be a move when enough of
its lines each relocated once.
"""

from __future__ import annotations

import re

from stale_script_refs import HISTORICAL_ROOTS

_FILENAME: re.Pattern[str] | None = None
# A colon range that is not already the tail of a path citation. ``file.py:12``
# has a word character before the colon, so it stays with the matcher. A
# decimal such as ``"min":118.22`` in a JSON measurement is a number, not a
# line, so a range followed by ``.<digit>`` never binds.
_BARE_RANGE = re.compile(r"(?<![\w./\\-]):(?P<start>\d+)(?:-(?P<end>\d+))?\b(?!\.\d)")
# Text formats this repository actually cites; extend when a real
# citation to a new format appears rather than enumerating every
# extension in existence (each entry adds matcher surface).
_EXTENSIONS = (
    "py|md|yml|yaml|json|jsonc|xml|csv|ps1|psm1|psd1|sh|ts|js|toml|txt|ini|cfg|html|css|ipynb"
)
# A repository-relative path. The basename is what a later bare range binds
# to. Segments of "." or "..", and a match stuck to a URL or an absolute
# path, are rejected by the caller or by the lookbehind.
_REPO_FILE = re.compile(
    rf"(?<![\w./\\-])(?P<path>(?:[\w.-]+/)+)(?P<name>[\w.-]+\.(?:{_EXTENSIONS}))\b"
)


def _file_pattern() -> re.Pattern[str]:
    """Return the filename pattern for a bare range."""
    global _FILENAME
    if _FILENAME is None:
        _FILENAME = re.compile(rf"(?<![\w./\\-])(?P<name>[\w.-]+\.(?:{_EXTENSIONS}))\b")
    return _FILENAME


def _basename_index(tracked: set[str]) -> dict[str, list[str]]:
    """Map a basename to the non-historical tracked files that use it."""
    index: dict[str, list[str]] = {}
    for path in tracked:
        if path.startswith(HISTORICAL_ROOTS):
            continue
        index.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    return index


def _resolve_unique_basename(name: str, index: dict[str, list[str]]) -> str | None:
    """Return the one tracked file named ``name``, or None when it is ambiguous."""
    candidates = index.get(name, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _expand_continuations(text: str, index: dict[str, list[str]]) -> str:
    """Bind a bare ``:N`` to the preceding filename when that name is unique.

    ``detect_agent_drift.py`` later in the paragraph as ``(:57-76)`` is the
    shape. An illustrative ``auth.ts:47`` is already a path citation and is
    not rewritten here. Ambiguous basenames stay bare so the gate skips them.
    """
    filename = _file_pattern()
    events: list[tuple[int, int, str, re.Match[str]]] = []
    for match in filename.finditer(text):
        events.append((match.start(), match.end(), "file", match))
    for match in _REPO_FILE.finditer(text):
        segments = [part for part in match.group("path").split("/") if part]
        if any(part in {".", ".."} for part in segments):
            continue
        events.append((match.start(), match.end(), "file", match))
    for match in _BARE_RANGE.finditer(text):
        events.append((match.start(), match.end(), "colon", match))
    events.sort(key=lambda item: (item[0], 0 if item[2] == "file" else 1))
    if not events:
        return text
    parts: list[str] = []
    cursor = 0
    last_name: str | None = None
    for start, end, kind, match in events:
        parts.append(text[cursor:start])
        if kind == "file":
            last_name = match.group("name")
            parts.append(text[start:end])
        else:
            resolved = _resolve_unique_basename(last_name, index) if last_name else None
            if resolved is None:
                parts.append(text[start:end])
            else:
                suffix = f"-{match.group('end')}" if match.group("end") else ""
                parts.append(f"{resolved}:{match.group('start')}{suffix}")
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _block_positions(block: list[str], lines: list[str]) -> list[int]:
    """Return every 1-based start where block sits verbatim in lines."""
    width = len(block)
    return [i + 1 for i in range(len(lines) - width + 1) if lines[i : i + width] == block]


def _unique_move(block: list[str], start: int, base: list[str], head: list[str]) -> int | None:
    """Return the block's single HEAD position, or None when the move is unproven.

    A cited block counts as moved only when it is distinctive (at least
    eight non-space characters), occurs exactly once at the merge base and
    exactly once at HEAD, and the HEAD copy is not at the cited start. A
    common line such as ``---`` or ``sys.executable,`` proves nothing.
    """
    if len("".join(text.strip() for text in block)) < 8:
        return None
    at_head = _block_positions(block, head)
    if len(_block_positions(block, base)) != 1 or len(at_head) != 1:
        return None
    return None if at_head[0] == start else at_head[0]


def _moved_cluster(
    start: int, end: int, base: list[str], head: list[str]
) -> tuple[int, int] | None:
    """Return where a stale range's unique lines went, when enough of them moved.

    The ordinary ratchet ignores a citation that was already wrong at the
    merge base. Four or more cited lines that each occur once at the base
    and once elsewhere at HEAD are evidence this change moved that text.
    The suggestion is the densest run of those new positions.
    """
    if not (1 <= start <= end <= len(base)) or not head:
        return None
    destinations: list[int] = []
    for number in range(start, end + 1):
        moved = _unique_move([base[number - 1]], number, base, head)
        if moved is not None:
            destinations.append(moved)
    if len(destinations) < 4:
        return None
    destinations.sort()
    width = max(end - start, 1)
    best: list[int] = []
    left = 0
    for right, dest in enumerate(destinations):
        while dest - destinations[left] > width:
            left += 1
        group = destinations[left : right + 1]
        if len(group) > len(best):
            best = group
    if len(best) < 2:
        return None
    return best[0], best[-1]


def _token_hit(anchor: str, text: str) -> bool:
    """Return whether anchor occurs as its own token, not inside a longer name."""
    normalized_anchor = " ".join(anchor.split())
    normalized_text = " ".join(text.split())
    if not normalized_anchor:
        return False
    return (
        re.search(rf"(?<![\w./-]){re.escape(normalized_anchor)}(?![\w./-])", normalized_text)
        is not None
    )


def _range_misses_distinctive_anchors(
    anchors: list[str], lines: list[str], start: int, end: int
) -> bool:
    """Return whether rare anchors named on the line miss the cited range.

    A rare anchor occurs on one or two lines. It votes inside only when
    every hit is inside the range. A hit on both sides does not vote.
    Two outside votes, and no inside vote, fail the citation.
    """
    if not anchors or not lines or start < 1 or end > len(lines):
        return False
    inside = 0
    outside = 0
    for anchor in anchors:
        hits = [number for number, text in enumerate(lines, 1) if _token_hit(anchor, text)]
        if not 1 <= len(hits) <= 2:
            continue
        in_range = [number for number in hits if start <= number <= end]
        if in_range and len(in_range) == len(hits):
            inside += 1
        elif not in_range:
            outside += 1
    return outside >= 2 and inside == 0
