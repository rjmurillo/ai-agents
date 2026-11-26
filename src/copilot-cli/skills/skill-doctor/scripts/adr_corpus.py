"""ADR folder discovery, ADR file parsing, and the finding record for adr_drift.py.

python3, stdlib only, no network, no git. adr_git.py runs git.

- The known-folder list equals skill-bootstrap's `KNOWN_FOLDERS` in
  `adr_locate.py`, which already holds adr-review's folders. A test pins both.
  Each skill installs on its own, so the list is copied, not imported.
- Filenames follow `ADR-NNN-slug.md` or the plain `NNNN-slug.md` form that
  adr-tools and MADR use, with one to six digits, as skill-bootstrap reads them:
  the prefix in any case, and `-` or `_` after the number. A test pins the match.
  skill-bootstrap also reads `.mdx` and `.adoc`. These checks parse Markdown, so
  such a file is listed in `rejected`, unread, and no folder is called missing.
  One difference is deliberate: skill-bootstrap numbers `2024-01-15-x.md` as ADR
  2024, while these checks list a date-named record in `rejected`, unnumbered.
- Every folder found is scanned, not only the first.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from adr_text import (
    ADR_MAX_BYTES,
    BACKTICK,
    clean_path,
    doc_status,
    h1_form,
    h1_number,
    parse_frontmatter,
    prose_lines,
)

KNOWN_DIRS = (
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
PREFIXED_NAME = re.compile(r"ADR-(\d{1,6})[-_](.+)\.md\Z", re.IGNORECASE | re.ASCII)
PLAIN_NAME = re.compile(r"(\d{1,6})[-_](.+)\.md\Z", re.IGNORECASE | re.ASCII)
UNREAD_NAME = re.compile(r"(?:ADR-)?\d{1,6}[-_].+\.(?:mdx|adoc)\Z", re.IGNORECASE | re.ASCII)
DATE_PREFIX = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|\d{8})(?!\d)")
INDEX_STEMS = frozenset({"readme", "index", "adr-index", "adr-log"})
DEFAULT_HEADINGS = ("Status", "Context", "Decision", "Consequences")
# `.adr-dir` holds one folder name; anything larger is not a marker.
MARKER_MAX_BYTES = 4096


class Finding(TypedDict):
    id: str
    kind: str
    group: str
    severity: str
    confidence: str
    evidence: dict[str, Any]
    suggested_fix: str


def make_finding(
    kind: str,
    group: str,
    severity: str,
    confidence: str,
    evidence: dict[str, Any],
    suggested_fix: str,
    key: Sequence[str],
) -> Finding:
    """Build one finding. `key` names the evidence fields that identify it."""
    digest = hashlib.sha256("\x1f".join((kind, *key)).encode("utf-8")).hexdigest()
    return {
        "id": digest[:12],
        "kind": kind,
        "group": group,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "suggested_fix": suggested_fix,
    }


@dataclass(frozen=True)
class AdrFile:
    path: Path
    rel: str
    convention: str
    number: int
    digits: int
    slug: str


@dataclass
class AdrDir:
    path: Path
    rel: str
    files: list[AdrFile]
    other_md: list[str]
    explicit: bool = False


@dataclass(frozen=True)
class FolderStyle:
    convention: str
    prefix: str
    width: int
    h1_form: str
    headings: tuple[str, ...]
    frontmatter_keys: tuple[str, ...]


@dataclass
class AdrDoc:
    file: AdrFile
    lines: list[str]
    frontmatter: dict[str, Any]
    frontmatter_lines: dict[str, int]
    body_start: int
    status: str


def parse_name(name: str) -> tuple[str, int, int, str] | None:
    """Return (convention, number, digits, slug) for an ADR filename, else None."""
    match = PREFIXED_NAME.match(name)
    if match:
        return "ADR-NNN", int(match.group(1)), len(match.group(1)), match.group(2)
    match = None if DATE_PREFIX.match(name) else PLAIN_NAME.match(name)
    if match:
        return "NNNN", int(match.group(1)), len(match.group(1)), match.group(2)
    return None


def is_template_name(name: str) -> bool:
    return "template" in name.lower()


def is_non_record_name(name: str) -> bool:
    """A template or an index or log file: never a numbered ADR.

    A date-named file never gets here: `load_dir` lists it in `rejected` first.
    """
    stem = name.lower().removesuffix(".md")
    return is_template_name(name) or stem in INDEX_STEMS


def within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass
class Survey:
    """Folders found, plus what could not be used or read, so no gap is silent."""

    dirs: list[AdrDir] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    read_errors: list[dict[str, str]] = field(default_factory=list)
    # True when an existing folder or ADR file was refused, for resolving outside the
    # repository or its folder or for a format this scan does not read, so ADRs may
    # exist unread.
    adrs_refused: bool = False


def path_exists(path: Path) -> bool:
    """`Path.exists`, reading any OS error as missing, as Python 3.14 does.

    Before 3.14, a name longer than the OS allows raises instead, so one long name
    in an ADR or `.adr-dir` would end the scan.
    """
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def path_is_dir(path: Path) -> bool:
    """`Path.is_dir`, reading any OS error as not a folder, like `path_exists`."""
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False


def _is_file(path: Path, rel: str, survey: Survey) -> bool:
    """`Path.is_file`. An OS error is a read error, not a crash: before 3.14 it raises."""
    try:
        return path.is_file()
    except (OSError, ValueError) as exc:
        survey.read_errors.append({"path": rel, "error": str(exc)})
        return False


def _resolve(path: Path) -> Path | None:
    """The real path, or None. A NUL byte (a UTF-16 `.adr-dir`) raises ValueError."""
    try:
        return path.resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def load_dir(path: Path, rel: str, survey: Survey, explicit: bool = False) -> AdrDir:
    """List one ADR folder, non-recursive. An entry that resolves outside the folder is rejected."""
    files: list[AdrFile] = []
    other: list[str] = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        survey.read_errors.append({"path": rel, "error": str(exc)})
        entries = []
    root = _resolve(path)
    for entry in entries:
        if UNREAD_NAME.match(entry.name) and _is_file(entry, f"{rel}/{entry.name}", survey):
            survey.adrs_refused = True
            survey.rejected.append(
                {"path": f"{rel}/{entry.name}", "reason": "a format this scan does not read"}
            )
            continue
        if entry.suffix.lower() != ".md" or not _is_file(entry, f"{rel}/{entry.name}", survey):
            continue
        target = _resolve(entry)
        if root is None or target is None or not within(target, root):
            survey.adrs_refused = True
            survey.rejected.append(
                {"path": f"{rel}/{entry.name}", "reason": "resolves outside the folder"}
            )
            continue
        parsed = parse_name(entry.name)
        if parsed is None and DATE_PREFIX.match(entry.name):
            # A date-named record: skill-bootstrap may number it; these checks do not.
            survey.adrs_refused = True
            survey.rejected.append(
                {"path": f"{rel}/{entry.name}", "reason": "a date-named record, not numbered"}
            )
            continue
        if parsed is None:
            other.append(entry.name)
            continue
        files.append(AdrFile(entry, f"{rel}/{entry.name}" if rel else entry.name, *parsed))
    files.sort(key=lambda f: (f.number, f.path.name))
    return AdrDir(path, rel, files, other, explicit)


def _marker_text(repo: Path, survey: Survey) -> str | None:
    """The `.adr-dir` text, or None. A symlink out of the repository, a device or FIFO,
    or a file over MARKER_MAX_BYTES is refused unread, so it cannot block or fill memory."""
    marker = repo / ".adr-dir"
    if not path_exists(marker):
        return None
    target = _resolve(marker)
    reason = None
    if target is None or not within(target, repo):
        reason = "resolves outside the repository"
    elif not _is_file(target, ".adr-dir", survey):
        reason = "is not a regular file"
    if reason is not None or target is None:
        survey.rejected.append({"path": ".adr-dir", "reason": reason})
        return None
    try:
        with target.open("rb") as handle:
            raw = handle.read(MARKER_MAX_BYTES + 1)
    except OSError as exc:
        survey.read_errors.append({"path": ".adr-dir", "error": str(exc)})
        return None
    if len(raw) > MARKER_MAX_BYTES:
        survey.rejected.append(
            {"path": ".adr-dir", "reason": f"larger than {MARKER_MAX_BYTES} bytes"}
        )
        return None
    return raw.decode("utf-8", errors="replace")


def _read_marker(repo: Path, survey: Survey) -> Path | None:
    """Return the folder named by an adr-tools `.adr-dir` file, or record why it is unusable."""
    text = _marker_text(repo, survey)
    if text is None:
        return None
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not first:
        survey.rejected.append({"path": ".adr-dir", "reason": "names no folder"})
        return None
    candidate = _resolve(repo / first)
    if candidate is None or not within(candidate, repo):
        if candidate is not None and path_is_dir(candidate):
            survey.adrs_refused = True
        survey.rejected.append(
            {"path": ".adr-dir", "reason": f"target {first} resolves outside the repository"}
        )
        return None
    if not path_is_dir(candidate):
        survey.rejected.append(
            {"path": ".adr-dir", "reason": f"target {first} is not a directory or is missing"}
        )
        return None
    return candidate


def _known_folder(repo: Path, rel: str, survey: Survey) -> Path | None:
    """The resolved known folder when it exists inside the repository, else None."""
    link = repo / rel
    path = _resolve(link)
    if path is None or not path_is_dir(path):
        if link.is_symlink():
            survey.rejected.append({"path": rel, "reason": "symlink target is missing"})
        return None
    if not within(path, repo):
        survey.adrs_refused = True
        survey.rejected.append({"path": rel, "reason": "resolves outside the repository"})
        return None
    return path


def find_adr_dirs(repo: Path) -> Survey:
    """Find ADR folders and the markers that led to them.

    A valid `.adr-dir` is authoritative and the only folder returned. Otherwise
    every known folder that holds a numbered ADR or a template counts. A known
    name that is an in-repository symlink is read once, under its real path, which
    is the path git logs. A second name for the same folder is skipped, as
    skill-bootstrap's `adr_locate._accept` skips a folder it has seen.
    """
    repo = repo.resolve()
    survey = Survey()
    marker = _read_marker(repo, survey)
    if marker is not None:
        rel = marker.relative_to(repo).as_posix()
        survey.dirs.append(load_dir(marker, rel, survey, explicit=True))
        survey.markers.append(".adr-dir")
        return survey
    seen: set[Path] = set()
    for name in KNOWN_DIRS:
        path = _known_folder(repo, name, survey)
        if path is None or path in seen:
            continue
        seen.add(path)
        rel = path.relative_to(repo).as_posix()
        loaded = load_dir(path, rel, survey)
        templates = [n for n in loaded.other_md if is_template_name(n)]
        if loaded.files or templates:
            survey.dirs.append(loaded)
        survey.markers.extend(f"template:{rel}/{name}" for name in templates)
    return survey


def next_number(dirs: Sequence[AdrDir]) -> int:
    """One more than the highest ADR number across every folder, or 1 when none."""
    numbers = [f.number for folder in dirs for f in folder.files]
    return (max(numbers) + 1) if numbers else 1


def newest_file(dirs: Sequence[AdrDir]) -> AdrFile | None:
    best: AdrFile | None = None
    for folder in dirs:
        for file in folder.files:
            if best is None or file.number > best.number:
                best = file
    return best


def find_h1(doc: AdrDoc) -> tuple[int, str] | None:
    """First H1 that carries an ADR number, as (line number, text)."""
    for number, text in prose_lines(doc.lines, doc.body_start):
        if text.startswith("# ") and h1_number(text) is not None:
            return number, text.rstrip()
    return None


def read_doc(file: AdrFile) -> AdrDoc:
    """Read and parse one ADR file. Raises OSError when it cannot be read or is too large."""
    size = file.path.stat().st_size
    if size > ADR_MAX_BYTES:
        raise OSError(f"{size} bytes, over the {ADR_MAX_BYTES}-byte limit for one ADR")
    text = file.path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    frontmatter, key_lines, body_start = parse_frontmatter(lines)
    status = doc_status(frontmatter, lines, body_start)
    return AdrDoc(file, lines, frontmatter, key_lines, body_start, status)


def read_docs(survey: Survey) -> list[AdrDoc]:
    """Read every ADR file. An unreadable file is recorded in `survey.read_errors`."""
    docs: list[AdrDoc] = []
    for folder in survey.dirs:
        for file in folder.files:
            try:
                docs.append(read_doc(file))
            except OSError as exc:
                _record_read_error(survey, file.rel, exc)
    return docs


def _record_read_error(survey: Survey, rel: str, exc: OSError) -> None:
    if all(entry["path"] != rel for entry in survey.read_errors):
        survey.read_errors.append({"path": rel, "error": str(exc)})


def folder_style(
    folder: AdrDir | None, dirs: Sequence[AdrDir] = (), survey: Survey | None = None
) -> FolderStyle:
    """Style a new record should follow: prefix, padding, H1 form, headings, frontmatter.

    When the newest ADR cannot be read, the style falls back to defaults and the
    failure goes to `survey.read_errors`, so a fallback is never silent.
    """
    pool = [folder] if folder is not None and folder.files else list(dirs)
    newest = newest_file(pool)
    if newest is None:
        return FolderStyle("ADR-NNN", "ADR-", 3, "adr-colon", DEFAULT_HEADINGS, ())
    counts = Counter(f.convention for d in pool for f in d.files)
    best = max(counts.values())
    convention = "ADR-NNN" if counts.get("ADR-NNN", 0) == best else "NNNN"
    prefix = "ADR-" if convention == "ADR-NNN" else ""
    try:
        doc: AdrDoc | None = read_doc(newest)
    except OSError as exc:
        doc = None
        if survey is not None:
            _record_read_error(survey, newest.rel, exc)
    form = "adr-colon" if convention == "ADR-NNN" else "number-dot"
    headings: tuple[str, ...] = DEFAULT_HEADINGS
    keys: tuple[str, ...] = ()
    if doc is not None:
        h1 = find_h1(doc)
        form = (h1 and h1_form(h1[1])) or form
        found = tuple(_h2_headings(doc))
        headings = found or DEFAULT_HEADINGS
        keys = tuple(doc.frontmatter)
    return FolderStyle(convention, prefix, newest.digits, form, headings, keys)


def _h2_headings(doc: AdrDoc) -> Iterator[str]:
    for _, line in prose_lines(doc.lines, doc.body_start):
        match = re.match(r"^##\s+(.*)$", line)
        # Trailing blanks and closing `#` marks come off in code: the old lazy regex was cubic.
        title = match.group(1).rstrip().rstrip("#").rstrip() if match else ""
        if title:
            yield title


def locate(repo: Path, survey: Survey) -> dict[str, Any]:
    """The `locate` subcommand result for a repository root and the folders found in it."""
    dirs = survey.dirs
    entries = []
    for folder in dirs:
        style = folder_style(folder, survey=survey)
        entries.append(
            {
                "path": folder.rel,
                "convention": style.convention,
                "prefix": style.prefix,
                "width": style.width,
                "h1_form": style.h1_form,
                "count": len(folder.files),
            }
        )
    reference = folder_style(None, dirs, survey)
    return {
        "repo": str(repo.resolve()),
        "adr_dirs": entries,
        "primary": entries[0]["path"] if len(entries) == 1 else None,
        "next_number": next_number(dirs),
        "template_headings": list(reference.headings) if dirs else [],
        "markers": list(survey.markers),
        "rejected": list(survey.rejected),
    }


def cited_paths(doc: AdrDoc) -> list[tuple[int, str]]:
    """Backticked repo-relative paths in prose, as (line, path), first sighting only."""
    seen: set[str] = set()
    found: list[tuple[int, str]] = []
    for number, line in prose_lines(doc.lines, doc.body_start):
        for token in BACKTICK.findall(line):
            path = clean_path(token)
            if path is not None and path not in seen:
                seen.add(path)
                found.append((number, path))
    return found
