# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts          (adrDirFor and nextAdrNumber, lines 14-41; renderAdr, slug,
#                                   lines 52-84, used by draft; the section kinds are in
#                                   adr_shape.py)
#   src/lib/fetchers/docs.ts       (ADR_DIR_CANDIDATES, lines 43-48; title and heading
#                                   reading of the ADR files, lines 70-110)
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_log.py, adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Find the repository's ADR folders and read their naming and heading style.

Reads the working tree only: directory listings and the newest ADR of each folder, never a
file over 1 MiB. Standard library only. Also holds the draft renderer, which fills the newest
ADR's headings from a scan candidate.

Departures from the upstream source, each pinned by a test:

- Detection order is an ``.adr-dir`` file (adr-tools), then every folder in ``KNOWN_FOLDERS``
  (adr-review's folders plus upstream's candidates), then, only when those find nothing, any
  folder holding three or more ADR-named files. Upstream had the known list alone.
- A file is an ADR when named ``ADR-NNN-slug``, ``adr-NNN-slug``, ``NNNN-slug`` or ``NNNN_slug``
  with an ``.md``, ``.mdx`` or ``.adoc`` extension. Upstream matched ``^(\\d+)-.*\\.md$`` and
  missed ``ADR-122-x.md``. A number has 1 to 6 digits, so a date-stamped name such as
  ``20240301-x.md`` is not an ADR number.
- A folder with no ADR-named file, such as one holding only ``README.md``, is not an ADR folder.
- The next number keeps the newest ADR's prefix and zero padding. The H1 form copies the newest
  ADR's H1 (``# ADR-123: Title``). Upstream always wrote ``# 123. Title``.
- A draft heading the source does not fill says ``Not recorded in the source.`` Every source
  field is one line, and a title that starts with Markdown syntax is escaped. A commit or pull
  request title loses its ``type(scope)!:`` prefix and trailing ``(#N)``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from adr_commits import iso_day, sanitize
from adr_docs import lines_outside_fences
from adr_shape import section_kind

__all__ = [
    "KNOWN_FOLDERS",
    "MAX_ADR_CHARS",
    "MAX_ADR_FILES",
    "MAX_READ_BYTES",
    "NOT_RECORDED",
    "NO_REASON",
    "NYGARD_HEADINGS",
    "FULL_SHA",
    "AdrFile",
    "AdrTally",
    "Style",
    "adr_files",
    "adr_title",
    "clean_source",
    "folder_style",
    "is_draft_target",
    "locate",
    "locate_folders",
    "read_adr_texts",
    "read_bounded",
    "render",
    "render_h1",
]

MAX_READ_BYTES = 1024 * 1024
MAX_ADR_FILES = 2000
MAX_ADR_CHARS = 32 * 1024 * 1024  # decoded characters, so not a byte count
MIN_SCAN_FILES = 3
_MAX_WALK_DIRS = 20000
_MAX_WALK_DEPTH = 8
NYGARD_HEADINGS: tuple[str, ...] = ("Status", "Context", "Decision", "Consequences")

# adr-review's folders, then upstream docs.ts lines 43-48 with its RFC folders. Pinned by a test.
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
# Blanks and closing marks come off in code: a lazy group before ``[ \t]*\Z`` is quadratic.
_H1 = re.compile(r"(?:#|=)[ \t]+(.+)", re.ASCII)
_H2 = re.compile(r"(?:##|==)[ \t]+(.+)", re.ASCII)
_H1_NUMBERED = re.compile(
    r"(?P<lead>(?:ADR|RFC|DR|Decision)?[ _-]?)(?P<num>[0-9]+)"
    r"(?P<sep>[ \t]*[:.)\-\u2013\u2014][ \t]*|[ \t]+)(?P<title>\S.*)\Z",
    re.IGNORECASE | re.ASCII,
)


@dataclass(frozen=True, slots=True)
class AdrFile:
    name: str
    number: int
    digits: str
    prefix: str


@dataclass(frozen=True, slots=True)
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
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as handle:
            data = handle.read(MAX_READ_BYTES + 1)
    except OSError:
        return None
    if len(data) > MAX_READ_BYTES:
        return None
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _skip_front_matter(text: str) -> str:
    """``text`` without its YAML front matter, which may hold a line that looks like a fence."""
    lines = text.split("\n")
    if lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return "\n".join(lines[index + 1 :])
    return text


def _first_h1(lines: list[str]) -> str | None:
    for line in lines:
        match = _H1.fullmatch(line.rstrip())
        if match and not line.startswith(("##", "==")):
            return match[1].rstrip(" \t")
    return None


def _without_closing_marks(title: str) -> str:
    """``title`` without a closing ``#`` or ``=`` run, which blanks set apart: ``C#`` keeps it."""
    body = title.rstrip("#=")
    return body.rstrip(" \t") if body != title and body[-1:] in ("", " ", "\t") else title


def _headings(lines: list[str]) -> tuple[str, ...]:
    found = (_H2.fullmatch(line.rstrip()) for line in lines)
    titles = (_without_closing_marks(match[1].rstrip(" \t")) for match in found if match)
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
    lines = lines_outside_fences(_skip_front_matter(text)) if text is not None else []
    headings = _headings(lines) or NYGARD_HEADINGS
    form = _h1_form(_first_h1(lines), newest.prefix, width)
    return Style(len(files), newest.prefix, width, highest, newest.name, form, headings)


def _adr_dir_file(root: Path) -> str | None:
    """The folder named by an adr-tools ``.adr-dir`` file, relative to the root."""
    text = read_bounded(root / ".adr-dir")
    name = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    return None if not name or "\x00" in name or Path(name).is_absolute() else name


def _walk_candidates(root: Path) -> tuple[list[str], bool]:
    """Folders holding ``MIN_SCAN_FILES`` or more ADR-named files, bounded and sorted, and a flag
    that is True when the walk stopped at ``_MAX_WALK_DIRS`` folders or did not enter the
    folders below ``_MAX_WALK_DEPTH`` levels. ``_SKIP_DIRS`` folders never count as a cut."""
    found: list[str] = []
    visited, truncated = 0, False
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
    declared = _adr_dir_file(root)
    return ([(declared, "adr-dir")] if declared else []) + [(rel, "known") for rel in KNOWN_FOLDERS]


def _resolved(path: Path) -> Path | None:
    try:  # Python before 3.13 raises RuntimeError on a symlink loop
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def _accept(root: Path, rel: str, seen: set[Path]) -> Path | None:
    """The real directory for ``rel`` when it is inside the root, new, and holds an ADR file."""
    target = _resolved(root / rel)
    if target is None or target in seen or root not in target.parents:
        return None
    if not target.is_dir() or not adr_files(target):
        return None
    seen.add(target)
    return target


def locate_folders(root: Path) -> tuple[list[tuple[str, str]], bool]:
    """Every ADR folder as ``(path relative to the root, source)``, sorted by path, and whether
    the walk was cut short (see ``_walk_candidates``). ``source`` is ``adr-dir``, ``known`` or
    ``scan``; the scan runs only when the first two find nothing.
    """
    seen: set[Path] = set()
    root = root.resolve()
    found: dict[str, str] = {}
    for rel, source in _declared(root):
        target = _accept(root, rel, seen)
        if target is not None:
            found.setdefault(_spelling(root, rel, target), source)
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
    """Whether ``draft`` may write into the folder. An RFC folder is read but takes no ADR."""
    return _RFC_FOLDER.fullmatch(PurePosixPath(rel).name) is None


def _spelling(root: Path, rel: str, target: Path) -> str:
    """``target`` from the root, or its RFC-named alias ``rel``, so the alias takes no draft."""
    real = target.relative_to(root).as_posix()
    alias = os.path.normpath(rel).replace(os.sep, "/")
    if is_draft_target(alias) or not is_draft_target(real) or _resolved(root / alias) != target:
        return real
    return alias


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
    """What ``read_adr_texts`` did, filled in as the stream runs: ``read`` files gave text,
    ``skipped`` were unreadable, over ``MAX_READ_BYTES``, or left unread after a cap, and
    ``cut`` is True when a cap left at least one file unread."""

    read: int = 0
    skipped: int = 0
    cut: bool = False


def read_adr_texts(
    root: Path, folders: list[tuple[str, str]] | None = None, tally: AdrTally | None = None
) -> Iterator[tuple[str, str]]:
    """Yield ``(relative path, text)`` of the ADR-named files, one at a time, newest first.

    ``folders`` is ``locate_folders(root)`` when the caller has it. Highest numbers come first,
    across folders. Reading stops after ``MAX_ADR_FILES`` files, or at the first file that would
    take the text past ``MAX_ADR_CHARS`` characters (an exact fit is read). ``tally.skipped``
    counts each file left unread that way, unreadable, or over ``MAX_READ_BYTES``.
    """
    tally = tally if tally is not None else AdrTally()
    root = root.resolve()
    total, full = 0, False
    pairs = locate_folders(root)[0] if folders is None else folders
    found = [(item, rel) for rel, _ in pairs for item in adr_files(root / rel)]
    for item, rel in sorted(found, key=lambda pair: pair[0].number, reverse=True):
        full = full or tally.read >= MAX_ADR_FILES
        text = None if full else read_bounded(root / rel / item.name)
        if text is not None and total + len(text) > MAX_ADR_CHARS:
            full, text = True, None
        if text is None:
            tally.skipped, tally.cut = tally.skipped + 1, tally.cut or full
            continue
        tally.read, total = tally.read + 1, total + len(text)
        yield f"{rel}/{item.name}", text


# Draft rendering: src/lib/adr-writer.ts, renderAdr
NOT_RECORDED = "Not recorded in the source."
NO_REASON = "The source states no reason."
_KIND_NOUN = {"pr": "pull request", "decision-log": "decision log entry"}
_TYPE_PREFIX = re.compile(r"\A[a-z]+(?:\([^)]*\))?!?:[ \t]+", re.IGNORECASE | re.ASCII)
_PR_SUFFIX = re.compile(r"\(#[0-9]+\)\Z", re.ASCII)
_URL = re.compile(r"https://[^\s<>`\"']+\Z", re.ASCII)
FULL_SHA = re.compile(r"[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64}", re.ASCII)
# Any leading ASCII punctuation may start structure (``<!--``, ``[x]: u``, ``___``), and a
# backslash before it is always a valid escape. A list number keeps its digits: ``12\. x``.
_MD_LEAD = re.compile(r"[!-/:-@\[-`{-~]", re.ASCII)
_LIST_NUMBER = re.compile(r"\A([0-9]+)([.)])(?=[ \t]|\Z)", re.ASCII)


def clean_source(source: object) -> dict[str, Any]:
    """The source fields the draft quotes, each string on one line. A ``sha`` or ``*_sha`` (such as
    ``reason_sha``) not of 40 or 64 hex digits, or a ``url`` or ``*_url`` (``pr_url``,
    ``reason_url``) not one ``https://`` word, is dropped, so no field can add a draft line."""
    cleaned: dict[str, Any] = {}
    for key, value in (source if isinstance(source, dict) else {}).items():
        text = " ".join(sanitize(value).splitlines()) if isinstance(value, str) else value
        pattern = {"sha": FULL_SHA, "url": _URL}.get(key.split("_")[-1])
        if pattern is None or (isinstance(text, str) and pattern.fullmatch(text)):
            cleaned[key] = text
    return cleaned


def _plain(text: str) -> str:
    """One line of ``text`` that cannot start Markdown structure: a backslash goes in front of a
    leading mark, so ``## x`` or a code fence shows as text."""
    return f"\\{text}" if _MD_LEAD.match(text) else _LIST_NUMBER.sub(r"\1\\\2", text, count=1)


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
    noun = _KIND_NOUN.get(candidate["kind"], "commit")
    source = candidate.get("source") or {}  # cleaned, so a dict
    cited = source.get("reason_url") or source.get("reason_sha")  # a PR's reason from a commit
    said = f"{reason} (stated in commit {cited})" if cited else reason
    parts = [f"The reason given at the time: {said}" if reason else NO_REASON]
    if excerpt:
        parts.append(f"From the source {noun}:\n\n{_quote(excerpt)}")
    return "\n\n".join(parts)


def _decision(candidate: dict[str, Any]) -> str:
    link = _link(candidate)
    return f"{_plain(candidate['title'])}\n\n" + (
        f"Decided in {link}" if link else "Where it was decided was not recorded."
    )


def render(style: Style, number: int, candidate: dict[str, Any], status: str) -> str:
    """The ADR text. Headings come from ``style``; the caller has cleaned the candidate."""
    day = iso_day(candidate.get("date"))
    kinds = [section_kind(heading) for heading in style.headings]
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
    # Context and decision always land (appended when missing); only a kind's first heading fills.
    sections = list(zip(style.headings, kinds, strict=True))
    sections += [(name.capitalize(), name) for name in ("context", "decision") if name not in kinds]
    used: set[str] = set()
    for heading, kind in sections:
        text = filled.get(kind, NOT_RECORDED) if kind not in used else NOT_RECORDED
        used.add(kind)
        lines += [f"## {heading}", "", text, ""]
    return "\n".join(lines)


def adr_title(kind: str, title: str) -> str:
    """Title for an ADR: a commit or PR title loses its ``type(scope)!:`` prefix and ``(#N)``."""
    if kind == "decision-log":
        return title
    cleaned = _PR_SUFFIX.sub("", _TYPE_PREFIX.sub("", title, count=1)).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else title
