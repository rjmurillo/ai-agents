"""ADR folder discovery, ADR file parsing, and the finding record for adr_drift.py.

python3, stdlib only, no network. Git runs through argument lists, never a shell.

Conventions:

- The known-folder list equals skill-bootstrap's `KNOWN_FOLDERS` in
  `adr_locate.py`, which already holds adr-review's folders. A test pins both.
  Each skill installs on its own, so the list is copied, not imported.
- Filenames follow `ADR-NNN-slug.md` or the plain `NNNN-slug.md` form that
  adr-tools and MADR use, with one to six digits, as skill-bootstrap reads them.
  skill-bootstrap also reads `.mdx`, `.adoc`, `_` separators, and a lowercase
  `adr-` prefix. These checks parse Markdown text, so they read `.md` files only.
- Every folder found is scanned, not only the first.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from adr_text import (
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
PREFIXED_NAME = re.compile(r"^ADR-(\d{1,6})-(.+)\.md$")
PLAIN_NAME = re.compile(r"^(\d{1,6})-(.+)\.md$")
DATE_PREFIX = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|\d{8})(?!\d)")
INDEX_STEMS = frozenset({"readme", "index", "adr-index", "adr-log"})
DEFAULT_HEADINGS = ("Status", "Context", "Decision", "Consequences")
GIT_TIMEOUT_SECONDS = 120
# The largest scan file adr_drift.py writes and report_adr.py reads.
SCAN_MAX_BYTES = 5_000_000

SETUP = "Setup"
NUMBERING = "Numbering"
LINKS = "Links"
HISTORY = "History"
GROUPS = (SETUP, NUMBERING, LINKS, HISTORY)


class Finding(TypedDict):
    id: str
    kind: str
    group: str
    severity: str
    confidence: str
    evidence: dict[str, Any]
    suggested_fix: str


class GitError(Exception):
    """A git command failed, timed out, or could not run.

    `returncode` is git's exit status when it ran and failed, else None.
    `timed_out` is True when the command hit GIT_TIMEOUT_SECONDS.
    """

    def __init__(
        self, message: str, returncode: int | None = None, timed_out: bool = False
    ) -> None:
        super().__init__(message)
        self._returncode = returncode
        self._timed_out = timed_out

    @property
    def returncode(self) -> int | None:
        return self._returncode

    @property
    def timed_out(self) -> bool:
        return self._timed_out


def run_git(repo: Path, args: Sequence[str]) -> str:
    """Run `git -C repo ARGS` with an argument list and return stdout."""
    argv = ["git", "-C", str(repo), "-c", "core.quotepath=off", *args]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=_git_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(
            f"git {args[0] if args else ''} timed out after {GIT_TIMEOUT_SECONDS} s", timed_out=True
        ) from exc
    except OSError as exc:
        raise GitError(f"git {args[0] if args else ''} could not run: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-1:] or ["no stderr"]
        raise GitError(
            f"git {args[0] if args else ''} exited {proc.returncode}: {tail[0]}", proc.returncode
        )
    return proc.stdout


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


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
    """A template, an index or log file, or a date-prefixed note: never a numbered ADR."""
    stem = name.lower().removesuffix(".md")
    return is_template_name(name) or stem in INDEX_STEMS or bool(DATE_PREFIX.match(name))


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
    # True when a folder exists but resolves outside the repository, so ADRs may exist unread.
    folder_outside: bool = False


def _resolve(path: Path) -> Path | None:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
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
        if entry.suffix != ".md" or not entry.is_file():
            continue
        target = _resolve(entry)
        if root is None or target is None or not within(target, root):
            survey.rejected.append(
                {"path": f"{rel}/{entry.name}", "reason": "resolves outside the folder"}
            )
            continue
        parsed = parse_name(entry.name)
        if parsed is None:
            other.append(entry.name)
            continue
        convention, number, digits, slug = parsed
        files.append(
            AdrFile(
                entry,
                f"{rel}/{entry.name}" if rel else entry.name,
                convention,
                number,
                digits,
                slug,
            )
        )
    files.sort(key=lambda f: (f.number, f.path.name))
    return AdrDir(path, rel, files, other, explicit)


def _read_marker(repo: Path, survey: Survey) -> Path | None:
    """Return the folder named by an adr-tools `.adr-dir` file, or record why it is unusable."""
    try:
        text = (repo / ".adr-dir").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    except OSError as exc:
        survey.read_errors.append({"path": ".adr-dir", "error": str(exc)})
        return None
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not first:
        survey.rejected.append({"path": ".adr-dir", "reason": "names no folder"})
        return None
    candidate = _resolve(repo / first)
    if candidate is None or not within(candidate, repo):
        survey.folder_outside = candidate is not None and candidate.is_dir()
        survey.rejected.append(
            {"path": ".adr-dir", "reason": f"target {first} resolves outside the repository"}
        )
        return None
    if not candidate.is_dir():
        survey.rejected.append(
            {"path": ".adr-dir", "reason": f"target {first} is not a directory or is missing"}
        )
        return None
    return candidate


def _known_folder(repo: Path, rel: str, survey: Survey) -> Path | None:
    """The resolved known folder when it exists inside the repository, else None."""
    link = repo / rel
    path = _resolve(link)
    if path is None or not path.is_dir():
        if link.is_symlink():
            survey.rejected.append({"path": rel, "reason": "symlink target is missing"})
        return None
    if not within(path, repo):
        survey.folder_outside = True
        survey.rejected.append({"path": rel, "reason": "resolves outside the repository"})
        return None
    return path


def find_adr_dirs(repo: Path) -> Survey:
    """Find ADR folders and the markers that led to them.

    A valid `.adr-dir` is authoritative and the only folder returned. Otherwise
    every known folder that holds a numbered ADR or a template counts.
    """
    repo = repo.resolve()
    survey = Survey()
    marker = _read_marker(repo, survey)
    if marker is not None:
        rel = marker.relative_to(repo).as_posix()
        survey.dirs.append(load_dir(marker, rel, survey, explicit=True))
        survey.markers.append(".adr-dir")
        return survey
    for rel in KNOWN_DIRS:
        path = _known_folder(repo, rel, survey)
        if path is None:
            continue
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
    """Read and parse one ADR file. Raises OSError when it cannot be read."""
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
                survey.read_errors.append({"path": file.rel, "error": str(exc)})
    return docs


def folder_style(folder: AdrDir | None, dirs: Sequence[AdrDir] = ()) -> FolderStyle:
    """Style a new record should follow: prefix, padding, H1 form, headings, frontmatter."""
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
    except OSError:
        doc = None
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
        match = re.match(r"^##\s+(.+?)\s*#*\s*$", line)
        if match:
            yield match.group(1)


def locate(repo: Path, survey: Survey) -> dict[str, Any]:
    """The `locate` subcommand result for a repository root and the folders found in it."""
    dirs = survey.dirs
    entries = []
    for folder in dirs:
        style = folder_style(folder)
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
    reference = folder_style(None, dirs)
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
