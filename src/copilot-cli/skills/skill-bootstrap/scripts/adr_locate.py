# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts          (adrDirFor and nextAdrNumber, lines 14-41; renderAdr, slug
#                                   and the section kinds, lines 52-84, used by draft)
#   src/lib/fetchers/docs.ts       (ADR_DIR_CANDIDATES, lines 43-48; title and heading
#                                   reading of the ADR files, lines 70-110)
# Sibling ports: adr_commits.py, adr_scan.py, bootstrap_adr.py, adr_docs.py.
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
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from adr_commits import iso_day

__all__ = [
    "ADR_EXTENSIONS",
    "KNOWN_FOLDERS",
    "MAX_READ_BYTES",
    "NOT_RECORDED",
    "NYGARD_HEADINGS",
    "AdrFile",
    "Style",
    "adr_files",
    "adr_title",
    "folder_style",
    "is_draft_target",
    "locate",
    "locate_folders",
    "read_adr_texts",
    "read_bounded",
    "render",
    "render_h1",
]

ADR_EXTENSIONS = (".md", ".mdx", ".adoc")
MAX_READ_BYTES = 1024 * 1024
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
_H1 = re.compile(r"(?:#|=)[ \t]+(.+?)[ \t]*\Z", re.ASCII)
_H2 = re.compile(r"(?:##|==)[ \t]+(.+?)[ \t#=]*\Z", re.ASCII)
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
            return match[1]
    return None


def _headings(lines: list[str]) -> tuple[str, ...]:
    found = (_H2.fullmatch(line.rstrip()) for line in lines)
    return tuple(match[1] for match in found if match and not match[1].startswith(("#", "=")))


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


def _walk_candidates(root: Path) -> list[str]:
    """Folders holding ``MIN_SCAN_FILES`` or more ADR-named files, bounded and sorted."""
    found: list[str] = []
    visited = 0
    for current, dirs, _files in os.walk(root, followlinks=False):
        visited += 1
        here = Path(current)
        depth = len(here.relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and depth < _MAX_WALK_DEPTH)
        if visited > _MAX_WALK_DIRS:
            break
        if len(adr_files(here)) >= MIN_SCAN_FILES and here != root:
            found.append(here.relative_to(root).as_posix())
    return found


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


def locate_folders(root: Path) -> list[tuple[str, str]]:
    """Every ADR folder as ``(path relative to the root, source)``, sorted by path.

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
    if not found:
        for rel in _walk_candidates(root):
            target = _accept(root, rel, seen)
            if target is not None:
                found[target.relative_to(root).as_posix()] = "scan"
    return sorted(found.items())


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
    folders = [_folder_payload(root.resolve(), rel, source) for rel, source in locate_folders(root)]
    targets = [folder for folder in folders if folder["draft_target"]]
    primary = targets[0] if len(targets) == 1 else None
    return {
        "folders": folders,
        "primary": primary["path"] if primary else None,
        "next_number": primary["next_number"] if primary else None,
        "examined": sum(folder["count"] for folder in folders),
    }


def read_adr_texts(root: Path) -> tuple[list[tuple[str, str]], int]:
    """``(relative path, text)`` of every ADR-named file in every folder, and how many were skipped.

    A file over ``MAX_READ_BYTES`` or unreadable is skipped and counted.
    """
    texts: list[tuple[str, str]] = []
    skipped = 0
    for rel, _source in locate_folders(root):
        for item in adr_files(root.resolve() / rel):
            text = read_bounded(root.resolve() / rel / item.name)
            if text is None:
                skipped += 1
            else:
                texts.append((f"{rel}/{item.name}", text))
    return texts, skipped


# ---------------------------------------------------------------------------
# Draft rendering (src/lib/adr-writer.ts, renderAdr)
# ---------------------------------------------------------------------------

NOT_RECORDED = "Not recorded in the source."
NO_REASON = "The source states no reason."
_TYPE_PREFIX = re.compile(r"\A[a-z]+(?:\([^)]*\))?!?:[ \t]+", re.IGNORECASE | re.ASCII)
_PR_SUFFIX = re.compile(r"[ \t]*\(#[0-9]+\)\Z", re.ASCII)
_URL = re.compile(r"https://[^\s<>`\"']+\Z", re.ASCII)
_SECTIONS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE | re.ASCII), kind)
    for pattern, kind in (
        (r"\bstatus\b", "status"),
        (r"\bdate\b", "date"),
        (
            r"\b(?:drivers?|options?|consequences?|confirmation|pros|cons|information|related"
            r"|links?|notes?)\b",
            "",
        ),
        (r"\b(?:context|background|problem|motivation|situation)\b", "context"),
        (r"\b(?:decision|outcome|chosen|resolution)\b", "decision"),
    )
)


def _link(candidate: dict[str, Any]) -> str:
    source = candidate.get("source")
    source = source if isinstance(source, dict) else {}
    url = source.get("url")
    if isinstance(url, str) and _URL.fullmatch(url):
        return url
    if candidate["kind"] == "decision-log":
        entry = str(source.get("entry_id") or "")
        return f"{source.get('file') or ''} (entry {entry})".strip()
    sha = source.get("sha")
    return f"commit {sha}" if isinstance(sha, str) and sha else ""


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def _context(candidate: dict[str, Any]) -> str:
    reason = candidate.get("reason")
    excerpt = (candidate.get("excerpt") or "").strip()
    noun = {"pr": "pull request", "decision-log": "decision log entry"}.get(
        candidate["kind"], "commit"
    )
    parts = [f"The reason given at the time: {reason}" if reason else NO_REASON]
    if excerpt:
        parts.append(f"From the source {noun}:\n\n{_quote(excerpt)}")
    return "\n\n".join(parts)


def _decision(candidate: dict[str, Any]) -> str:
    link = _link(candidate)
    return f"{candidate['title']}\n\n" + (
        f"Decided in {link}" if link else "Where it was decided was not recorded."
    )


def _section_kind(heading: str) -> str:
    return next((kind for pattern, kind in _SECTIONS if pattern.search(heading)), "")


def render(style: Style, number: int, candidate: dict[str, Any], status: str) -> str:
    """The ADR text. Headings come from ``style``; an unfilled heading says so.

    The candidate's text fields must already be cleaned by the caller.
    """
    day = iso_day(candidate.get("date"))
    kinds = [_section_kind(heading) for heading in style.headings]
    lines = [render_h1(style.h1_form, number, candidate["title"]), ""]
    header = ([f"Date: {day}"] if day and "date" not in kinds else []) + (
        [f"Status: {status}"] if "status" not in kinds else []
    )
    if header:
        lines += [*header, ""]
    filled = {
        "status": status,
        "date": day or NOT_RECORDED,
        "context": _context(candidate),
        "decision": _decision(candidate),
    }
    # The source text must always land somewhere: a folder whose newest ADR has no context or
    # decision heading gets one appended. Only the first heading of each kind is filled.
    sections = list(zip(style.headings, kinds, strict=True))
    sections += [(name.capitalize(), name) for name in ("context", "decision") if name not in kinds]
    used: set[str] = set()
    for heading, kind in sections:
        text = filled.get(kind, NOT_RECORDED) if kind not in used else NOT_RECORDED
        used.add(kind)
        lines += [f"## {heading}", "", text, ""]
    return "\n".join(lines)


def adr_title(kind: str, title: str) -> str:
    """The ADR title for a source title: a commit or pull request loses its conventional
    ``type(scope)!:`` prefix and its trailing ``(#N)``. Upstream keeps both."""
    if kind == "decision-log":
        return title
    cleaned = _PR_SUFFIX.sub("", _TYPE_PREFIX.sub("", title, count=1)).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else title
