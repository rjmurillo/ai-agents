"""ADR folder discovery, ADR file parsing, and the finding record for adr_drift.py.

Stdlib only, Python 3.10+, no network. Git runs through argument lists, never a shell.

Conventions:

- The known-folder list matches the adr-review skill's `detect_adr_changes.py`
  (`.project-toolkit/architecture`, `docs/adr`, `docs/architecture`,
  `docs/decisions`, `architecture/decisions`) plus the adr-tools default
  `doc/adr`. A test pins that the adr-review folders stay a subset.
- Filenames follow `ADR-NNN-slug.md`, widened to digit runs of any length and
  to the plain `NNNN-slug.md` form that adr-tools and MADR use.
- Every folder found is scanned, not only the first.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KNOWN_DIRS = (
    ".project-toolkit/architecture",
    "docs/adr",
    "docs/architecture",
    "docs/decisions",
    "architecture/decisions",
    "doc/adr",
)
PREFIXED_NAME = re.compile(r"^ADR-(\d+)-(.+)\.md$")
PLAIN_NAME = re.compile(r"^(\d+)-(.+)\.md$")
DEFAULT_HEADINGS = ("Status", "Context", "Decision", "Consequences")
GIT_TIMEOUT_SECONDS = 120

Finding = dict[str, Any]


class GitError(Exception):
    """A git command failed or git is missing."""


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
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {args[0] if args else ''} could not run: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-1:] or ["no stderr"]
        raise GitError(f"git {args[0] if args else ''} exited {proc.returncode}: {tail[0]}")
    return proc.stdout


def _git_env() -> dict[str, str]:
    import os

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
    body_start: int
    status: str


def parse_name(name: str) -> tuple[str, int, int, str] | None:
    """Return (convention, number, digits, slug) for an ADR filename, else None."""
    match = PREFIXED_NAME.match(name)
    if match:
        return "ADR-NNN", int(match.group(1)), len(match.group(1)), match.group(2)
    match = PLAIN_NAME.match(name)
    if match:
        return "NNNN", int(match.group(1)), len(match.group(1)), match.group(2)
    return None


def is_template_name(name: str) -> bool:
    return "template" in name.lower()


def within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def load_dir(path: Path, rel: str, explicit: bool = False) -> AdrDir:
    """List one ADR folder, non-recursive. Unreadable folders list as empty."""
    files: list[AdrFile] = []
    other: list[str] = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name)
    except OSError:
        entries = []
    for entry in entries:
        if entry.suffix != ".md" or not entry.is_file():
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


def _read_marker(repo: Path) -> Path | None:
    """Return the folder named by an adr-tools `.adr-dir` file, when valid."""
    try:
        text = (repo / ".adr-dir").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not first:
        return None
    candidate = (repo / first).resolve()
    if candidate.is_dir() and within(candidate, repo):
        return candidate
    return None


def find_adr_dirs(repo: Path) -> tuple[list[AdrDir], list[str]]:
    """Find ADR folders and the markers that led to them.

    A valid `.adr-dir` is authoritative and the only folder returned. Otherwise
    every known folder that holds a numbered ADR or a template counts.
    """
    repo = repo.resolve()
    marker = _read_marker(repo)
    if marker is not None:
        rel = marker.relative_to(repo).as_posix()
        return [load_dir(marker, rel, explicit=True)], [".adr-dir"]
    found: list[AdrDir] = []
    markers: list[str] = []
    for rel in KNOWN_DIRS:
        path = (repo / rel).resolve()
        # A symlinked folder that leaves the repository is not this repo's ADR folder.
        if not path.is_dir() or not within(path, repo):
            continue
        loaded = load_dir(path, rel)
        templates = [n for n in loaded.other_md if is_template_name(n)]
        if loaded.files or templates:
            found.append(loaded)
        markers.extend(f"template:{rel}/{name}" for name in templates)
    return found, markers


def newest_file(dirs: Sequence[AdrDir]) -> AdrFile | None:
    best: AdrFile | None = None
    for folder in dirs:
        for file in folder.files:
            if best is None or file.number > best.number:
                best = file
    return best


def parse_frontmatter(lines: Sequence[str]) -> tuple[dict[str, Any], int]:
    """Parse simple top-level YAML keys. Returns (keys, index of first body line)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    keys: dict[str, Any] = {}
    current: str | None = None
    for index in range(1, min(len(lines), 80)):
        line = lines[index]
        if line.strip() == "---":
            return keys, index + 1
        top = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if top:
            current = top.group(1)
            keys[current] = _scalar(top.group(2))
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current is not None:
            existing = keys[current]
            values = existing if isinstance(existing, list) else []
            values.append(_strip_comment(item.group(1)))
            keys[current] = values
    return {}, 0


def _strip_comment(value: str) -> str:
    return re.sub(r"\s+#.*$", "", value).strip().strip("'\"")


def _scalar(raw: str) -> Any:
    value = _strip_comment(raw)
    if value.startswith("[") and value.endswith("]"):
        return [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
    return value


def prose_lines(lines: Sequence[str], start: int = 0) -> Iterator[tuple[int, str]]:
    """Yield (1-based line number, text), skipping fenced code and HTML comments."""
    fenced = False
    commented = False
    for index in range(start, len(lines)):
        line = lines[index]
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if commented:
            commented = "-->" not in line
            continue
        if stripped.startswith("<!--") and "-->" not in line:
            commented = True
            continue
        yield index + 1, line


def h1_number(text: str) -> int | None:
    match = re.match(r"^#\s+ADR-0*(\d+)\b", text) or re.match(r"^#\s+0*(\d+)\.\s", text)
    return int(match.group(1)) if match else None


def h1_form(text: str) -> str | None:
    if re.match(r"^#\s+ADR-\d+\s*:", text):
        return "adr-colon"
    if re.match(r"^#\s+\d+\.\s", text):
        return "number-dot"
    return None


def find_h1(doc: AdrDoc) -> tuple[int, str] | None:
    """First H1 that carries an ADR number, as (line number, text)."""
    for number, text in prose_lines(doc.lines, doc.body_start):
        if text.startswith("# ") and h1_number(text) is not None:
            return number, text.rstrip()
    return None


def doc_status(frontmatter: dict[str, Any], lines: Sequence[str], start: int) -> str:
    """Lowercase status text: frontmatter first, then a Status section or line."""
    value = frontmatter.get("status")
    if isinstance(value, str) and value:
        return value.lower()
    in_section = False
    for _, line in prose_lines(lines, start):
        if re.match(r"^#{2,3}\s+status\b", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if line.startswith("#"):
                return ""
            if line.strip():
                return line.strip().lower()
            continue
        inline = re.match(r"^\s*(?:[-*]\s+)?\**status\**\s*[:|]\s*\**\s*(.+)$", line, re.IGNORECASE)
        if inline:
            return inline.group(1).strip().lower()
    return ""


def status_word(status: str) -> str:
    match = re.match(r"[a-z]+", status.strip("*_ ").lower())
    return match.group(0) if match else ""


def read_doc(file: AdrFile) -> AdrDoc | None:
    try:
        text = file.path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    frontmatter, body_start = parse_frontmatter(lines)
    return AdrDoc(file, lines, frontmatter, body_start, doc_status(frontmatter, lines, body_start))


def read_docs(dirs: Sequence[AdrDir]) -> list[AdrDoc]:
    docs = (read_doc(f) for folder in dirs for f in folder.files)
    return [doc for doc in docs if doc is not None]


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
    doc = read_doc(newest)
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


def locate(repo: Path) -> dict[str, Any]:
    """The `locate` subcommand result for a repository root."""
    dirs, markers = find_adr_dirs(repo)
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
    numbers = [f.number for folder in dirs for f in folder.files]
    reference = folder_style(None, dirs)
    return {
        "repo": str(repo.resolve()),
        "adr_dirs": entries,
        "primary": entries[0]["path"] if len(entries) == 1 else None,
        "next_number": (max(numbers) + 1) if numbers else 1,
        "template_headings": list(reference.headings) if dirs else [],
        "markers": markers,
    }
