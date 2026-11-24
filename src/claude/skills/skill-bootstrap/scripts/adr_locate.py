# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts          (adrDirFor and nextAdrNumber, lines 14-41; renderAdr is in
#                                   adr_render.py)
#   src/lib/fetchers/docs.ts       (ADR_DIR_CANDIDATES, lines 43-48; title and heading
#                                   reading of the ADR files, lines 70-110)
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_render.py, adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Find the repository's ADR folders and read their naming and heading style.

Reads the working tree only: directory listings and the newest ADR of each folder, never
a file over 1 MiB. Standard library only.

Departures from the upstream source, each pinned by a test:

- Detection order is an ``.adr-dir`` file (adr-tools), then every folder in ``KNOWN_FOLDERS``
  (adr-review's folders plus upstream's candidates), then, only when those find nothing,
  any folder holding three or more ADR-named files. Upstream had the known list alone.
- A file counts as an ADR when its name is ``ADR-NNN-slug``, ``adr-NNN-slug``,
  ``NNNN-slug`` or ``NNNN_slug`` with an ``.md``, ``.mdx`` or ``.adoc`` extension. Upstream
  matched ``^(\\d+)-.*\\.md$`` and missed ``ADR-122-x.md``. A number has 1 to 6 digits, so a
  date-stamped name such as ``20240301-x.md`` is not an ADR number.
- A folder with no ADR-named file, such as one holding only ``README.md``, is not an ADR folder.
- The next number keeps the newest ADR's prefix and zero padding.
- The H1 form copies the newest ADR's H1 (``# ADR-123: Title``). Upstream always wrote
  ``# 123. Title``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = [
    "ADR_EXTENSIONS",
    "KNOWN_FOLDERS",
    "MAX_ADR_BYTES",
    "MAX_ADR_FILES",
    "MAX_READ_BYTES",
    "NYGARD_HEADINGS",
    "AdrFile",
    "AdrTally",
    "Style",
    "adr_files",
    "folder_style",
    "is_draft_target",
    "locate",
    "locate_folders",
    "read_adr_texts",
    "read_bounded",
    "render_h1",
]

ADR_EXTENSIONS = (".md", ".mdx", ".adoc")
MAX_READ_BYTES = 1024 * 1024
MAX_ADR_FILES = 2000
MAX_ADR_BYTES = 32 * 1024 * 1024
MIN_SCAN_FILES = 3
_MAX_WALK_DIRS = 20000
_MAX_WALK_DEPTH = 8
NYGARD_HEADINGS: tuple[str, ...] = ("Status", "Context", "Decision", "Consequences")

# adr-review's monitored folders first, then upstream docs.ts lines 43-48 (including its RFC
# folders). One constant, pinned by a test, so a change shows up in review.
KNOWN_FOLDERS: tuple[str, ...] = (
    ".project-toolkit/architecture",
    "docs/architecture",
    "docs/decisions",
    "docs/adr",
    "architecture/decisions",
    "doc/adr",
    "doc/decisions",
    "adr",
    "docs/adrs",
    "src/docs/adrs",
    "src/docs/adr",
    "docs/architecture/adr",
    "docs/architecture/decisions",
    "docs/rfcs",
    "docs/rfc",
    "rfcs",
    "rfc",
)
_SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", "vendor"}
)

_ADR_NAME = re.compile(
    r"(?P<prefix>adr-)?(?P<num>[0-9]{1,6})[-_](?P<slug>.+)\.(?:md|mdx|adoc)\Z",
    re.IGNORECASE | re.ASCII,
)
_FENCE = re.compile(r"\s{0,3}(?:`{3,}|~{3,})", re.ASCII)
# The trailing blanks and closing marks come off in code: a lazy group followed by ``[ \t]*\Z``
# is quadratic on a long run of spaces.
_H1 = re.compile(r"(?:#|=)[ \t]+(.+)", re.ASCII)
_H2 = re.compile(r"(?:##|==)[ \t]+(.+)", re.ASCII)
_H1_NUMBERED = re.compile(
    r"(?P<lead>(?:ADR|RFC|DR|Decision)?[ _-]?)(?P<num>[0-9]+)"
    r"(?P<sep>[ \t]*[:.)\-\u2013\u2014][ \t]*|[ \t]+)(?P<title>\S.*)\Z",
    re.IGNORECASE | re.ASCII,
)


@dataclass(frozen=True)
class AdrFile:
    name: str
    number: int
    digits: str
    prefix: str


@dataclass(frozen=True)
class Style:
    """The naming and heading conventions of one ADR folder."""

    count: int
    prefix: str
    width: int
    highest: int
    newest: str | None
    h1_form: str
    headings: tuple[str, ...]


def adr_files(directory: Path) -> list[AdrFile]:
    """The ADR-named regular files of ``directory``. Symlinks are not followed."""
    found: list[AdrFile] = []
    try:
        with os.scandir(directory) as scan:
            names = sorted(entry.name for entry in scan if entry.is_file(follow_symlinks=False))
    except OSError:
        return found
    for name in names:
        match = _ADR_NAME.fullmatch(name)
        if match:
            digits = match["num"]
            found.append(AdrFile(name, int(digits), digits, match["prefix"] or ""))
    return found


def read_bounded(path: Path) -> str | None:
    """File text, or None when unreadable, not a regular file, or over ``MAX_READ_BYTES``."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_READ_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _lines_outside_fences(text: str) -> list[str]:
    lines: list[str] = []
    in_fence = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            lines.append(line)
    return lines


def _skip_front_matter(lines: list[str]) -> list[str]:
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return lines[index + 1 :]
    return lines


def _first_h1(lines: list[str]) -> str | None:
    for line in lines:
        match = _H1.fullmatch(line.rstrip())
        if match and not line.startswith(("##", "==")):
            return match[1].rstrip(" \t")
    return None


def _headings(lines: list[str]) -> tuple[str, ...]:
    found = (_H2.fullmatch(line.rstrip()) for line in lines)
    titles = (match[1].rstrip(" \t#=") for match in found if match)
    return tuple(title for title in titles if title and not title.startswith(("#", "=")))


def _h1_form(h1: str | None, prefix: str, width: int) -> str:
    """A format string with ``{number}`` and ``{title}`` that reproduces the H1 style."""
    if h1 is not None:
        match = _H1_NUMBERED.fullmatch(h1)
        if match is None:
            return "# {title}"
        digits = match["num"]
        spec = f"0{len(digits)}d" if digits.startswith("0") and len(digits) > 1 else ""
        field = "{number:" + spec + "}" if spec else "{number}"
        return f"# {match['lead']}{field}{match['sep']}{{title}}"
    if prefix or width > 1:
        return "# " + prefix + "{number:0" + str(width) + "d}: {title}"
    return "# {number}. {title}"


def render_h1(form: str, number: int, title: str) -> str:
    """Fill an H1 form. The title is an argument, so braces in it are plain text."""
    return form.format(number=number, title=title)


def _newest(files: list[AdrFile]) -> AdrFile:
    return max(files, key=lambda item: (item.number, len(item.digits), item.name))


def folder_style(directory: Path) -> Style:
    """Read the style of ``directory``. An empty or missing folder gets the Nygard defaults."""
    files = adr_files(directory)
    if not files:
        return Style(0, "", 4, 0, None, "# {number}. {title}", NYGARD_HEADINGS)
    newest = _newest(files)
    highest = newest.number
    width = max(len(item.digits) for item in files if item.number == highest)
    text = read_bounded(directory / newest.name)
    lines = _skip_front_matter(_lines_outside_fences(text)) if text is not None else []
    headings = _headings(lines) or NYGARD_HEADINGS
    form = _h1_form(_first_h1(lines), newest.prefix, width)
    return Style(len(files), newest.prefix, width, highest, newest.name, form, headings)


def _within(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _adr_dir_file(root: Path) -> str | None:
    """The folder named by an adr-tools ``.adr-dir`` file, relative to the root."""
    text = read_bounded(root / ".adr-dir")
    name = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    if not name or "\x00" in name or Path(name).is_absolute():
        return None
    return name


def _walk_candidates(root: Path) -> tuple[list[str], bool]:
    """Folders holding ``MIN_SCAN_FILES`` or more ADR-named files, bounded and sorted.

    The flag is True when the walk stopped at ``_MAX_WALK_DIRS`` folders or did not enter the
    folders below ``_MAX_WALK_DEPTH`` levels. Folders in ``_SKIP_DIRS`` are never entered and
    never count as a cut.
    """
    found: list[str] = []
    visited = 0
    truncated = False
    for current, dirs, _files in os.walk(root, followlinks=False):
        visited += 1
        here = Path(current)
        depth = len(here.relative_to(root).parts)
        below = sorted(d for d in dirs if d not in _SKIP_DIRS)
        if below and depth >= _MAX_WALK_DEPTH:
            truncated, below = True, []
        dirs[:] = below
        if visited > _MAX_WALK_DIRS:
            return found, True
        if len(adr_files(here)) >= MIN_SCAN_FILES and here != root:
            found.append(here.relative_to(root).as_posix())
    return found, truncated


def _declared(root: Path) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    declared = _adr_dir_file(root)
    if declared:
        names.append((declared, "adr-dir"))
    names.extend((rel, "known") for rel in KNOWN_FOLDERS)
    return names


def _accept(root: Path, rel: str, seen: set[Path]) -> Path | None:
    """The real directory for ``rel`` when it is inside the root, new, and holds an ADR file."""
    target = (root / rel).resolve()
    if not _within(root, target) or target == root or target in seen or not target.is_dir():
        return None
    if not adr_files(target):
        return None
    seen.add(target)
    return target


def locate_folders(root: Path) -> tuple[list[tuple[str, str]], bool]:
    """Every ADR folder as ``(path relative to the root, source)``, sorted by path, and whether
    the directory walk was cut short (see ``_walk_candidates``).

    ``source`` is ``adr-dir``, ``known`` or ``scan``. The scan runs only when the first
    two sources find nothing.
    """
    seen: set[Path] = set()
    root = root.resolve()
    found: dict[str, str] = {}
    for rel, source in _declared(root):
        target = _accept(root, rel, seen)
        if target is not None:
            found.setdefault(target.relative_to(root).as_posix(), source)
    truncated = False
    if not found:
        walked, truncated = _walk_candidates(root)
        for rel in walked:
            target = _accept(root, rel, seen)
            if target is not None:
                found[target.relative_to(root).as_posix()] = "scan"
    return sorted(found.items()), truncated


_RFC_FOLDER = re.compile(r"rfcs?", re.IGNORECASE)


def is_draft_target(rel: str) -> bool:
    """Whether ``draft`` may write into the folder. An RFC folder is read, so its links still
    hide decisions, but it never takes an ADR (upstream ``adr-writer.ts`` line 18 also skips it)."""
    return _RFC_FOLDER.fullmatch(PurePosixPath(rel).name) is None


def _folder_payload(root: Path, rel: str, source: str) -> dict[str, Any]:
    style = folder_style(root / rel)
    return {
        "path": rel,
        "source": source,
        "count": style.count,
        "prefix": style.prefix,
        "width": style.width,
        "highest": style.highest,
        "next_number": style.highest + 1,
        "newest": style.newest,
        "h1_form": style.h1_form,
        "headings": list(style.headings),
        "draft_target": is_draft_target(rel),
    }


def locate(root: Path) -> dict[str, Any]:
    """The ``locate`` payload: folders, the single primary folder or None, and the next number."""
    found, truncated = locate_folders(root)
    folders = [_folder_payload(root.resolve(), rel, source) for rel, source in found]
    targets = [folder for folder in folders if folder["draft_target"]]
    primary = targets[0] if len(targets) == 1 else None
    return {
        "folders": folders,
        "primary": primary["path"] if primary else None,
        "next_number": primary["next_number"] if primary else None,
        "examined": sum(folder["count"] for folder in folders),
        "walk_truncated": truncated,
    }


@dataclass
class AdrTally:
    """What ``read_adr_texts`` did, filled in as the stream runs.

    ``read`` files gave text, ``skipped`` were unreadable, over ``MAX_READ_BYTES``, or left
    unread after a cap, and ``cut`` is True when a cap left at least one file unread.
    """

    read: int = 0
    skipped: int = 0
    cut: bool = False


def read_adr_texts(
    root: Path, folders: list[tuple[str, str]] | None = None, tally: AdrTally | None = None
) -> Iterator[tuple[str, str]]:
    """Yield ``(relative path, text)`` of the ADR-named files, one file at a time.

    ``folders`` is the result of ``locate_folders(root)`` when the caller already has it. Reading
    stops after ``MAX_ADR_FILES`` files or ``MAX_ADR_BYTES`` characters. A file not read for that
    reason, and a file unreadable or over ``MAX_READ_BYTES``, is counted in ``tally.skipped``.
    """
    tally = tally if tally is not None else AdrTally()
    root = root.resolve()
    total = 0
    for rel, _source in locate_folders(root)[0] if folders is None else folders:
        for item in adr_files(root / rel):
            if tally.read >= MAX_ADR_FILES or total >= MAX_ADR_BYTES:
                tally.skipped, tally.cut = tally.skipped + 1, True
                continue
            text = read_bounded(root / rel / item.name)
            if text is None:
                tally.skipped += 1
                continue
            tally.read, total = tally.read + 1, total + len(text)
            yield f"{rel}/{item.name}", text
