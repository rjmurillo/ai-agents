# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream file: src/lib/adr-writer.ts (renderAdr, slug and writeAdr, lines 52-84 and
#   137-148). The trailing "Drafted by" comment of renderAdr is not ported.
# Sibling ports: adr_text.py, adr_locate.py, adr_scan.py, adr_prs.py, adr_log.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Render one candidate from a scan file as an ADR and create it. Never replaces a file.

Everything in the draft comes from the source: its title, the reason it stated, an excerpt
of its text, and a link to where it was decided. Nothing is generated, so a section the
source never covered says so.

Departures from the upstream source, each pinned by a test:

- The status is ``Proposed`` by default. A person accepts the ADR through review. Upstream
  wrote ``Accepted``.
- The H1 copies the newest ADR's form (``# ADR-123: Title``) and the file name keeps its
  prefix and zero padding. Upstream wrote ``# 123. Title`` and a bare number.
- The headings follow the newest ADR in the folder. A heading the source does not fill says
  ``Not recorded in the source.`` Upstream wrote fixed Nygard headings.
- The number is chosen at write time from the folder, then the file is created with mode
  ``x``. A name that exists is reported and never retried with another number.
- A title with no ASCII letter or digit gives the slug ``decision-<sha7>`` (or the id), not ``""``.
- A target inside the repository must be one of the located ADR folders and must not be
  ignored by git.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from adr_git import ConfigError, git_bytes, git_text, repo_root
from adr_locate import (
    MAX_READ_BYTES,
    Style,
    adr_files,
    folder_style,
    is_draft_target,
    locate_folders,
    render_h1,
)
from adr_text import iso_day, sanitize, slugify

__all__ = ["ExistsError", "NOT_RECORDED", "draft", "load_candidate", "render"]

NOT_RECORDED = "Not recorded in the source."
NO_REASON = "The source states no reason."
_TYPE_PREFIX = re.compile(r"\A[a-z]+(?:\([^)]*\))?!?:[ \t]+", re.IGNORECASE | re.ASCII)
_PR_SUFFIX = re.compile(r"[ \t]*\(#[0-9]+\)\Z", re.ASCII)
_KINDS = frozenset({"commit", "pr", "decision-log"})
_STATUS = re.compile(r"[A-Za-z][A-Za-z -]{0,39}\Z", re.ASCII)
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


class ExistsError(Exception):
    """The target exists, or another ADR took the same number. Exit 1."""

    def __init__(self, message: str, path: Path, others: list[str] | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.others = others or []


def _text(value: object, name: str, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ConfigError(f"scan file candidate field {name!r} must be a string")
    return sanitize(value)


def load_candidate(path: str, ident: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a scan file and return ``(scan, candidate)`` for ``ident``, or raise ConfigError."""
    target = Path(path)
    try:
        if target.stat().st_size > 16 * MAX_READ_BYTES:
            raise ConfigError(f"scan file {path} is too large")
        data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read scan file {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise ConfigError(f"scan file {path} is not a scan result")
    if not isinstance(data.get("repo"), str):
        raise ConfigError(f"scan file {path} does not name its repository")
    for item in data["candidates"]:
        if isinstance(item, dict) and item.get("id") == ident:
            return data, item
    raise ConfigError(f"no candidate with id {ident!r} in {path}")


def _link(candidate: dict[str, Any]) -> str:
    source = candidate.get("source")
    source = source if isinstance(source, dict) else {}
    url = source.get("url")
    if isinstance(url, str) and _URL.fullmatch(url):
        return url
    if candidate["kind"] == "decision-log":
        entry = sanitize(str(source.get("entry_id") or ""))
        return f"{sanitize(str(source.get('file') or ''))} (entry {entry})".strip()
    sha = source.get("sha")
    return f"commit {sanitize(sha)}" if isinstance(sha, str) and sha else ""


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def _context(candidate: dict[str, Any]) -> str:
    reason = _text(candidate.get("reason"), "reason")
    excerpt = (_text(candidate.get("excerpt"), "excerpt") or "").strip()
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
    """The ADR text. Headings come from ``style``; an unfilled heading says so."""
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


def _check_candidate(candidate: dict[str, Any]) -> None:
    if candidate.get("kind") not in _KINDS:
        raise ConfigError(f"candidate {candidate.get('id')!r} has an unknown kind")
    title = (_text(candidate.get("title"), "title", True) or "").strip()
    candidate["title"] = adr_title(candidate["kind"], title)


def _git_path(directory: Path, flag: str) -> Path | None:
    proc = git_bytes(directory, "rev-parse", flag)
    text = proc.stdout.decode("utf-8", "replace").strip()
    return (directory / text).resolve() if proc.returncode == 0 and text else None


def _gate_tree(root: Path, out_dir: Path) -> Path | None:
    """The work tree that ``out_dir`` lies in, when draft must gate on it.

    That is the scanned work tree, or another work tree of the same repository (a linked
    worktree), found by asking git where the nearest existing ancestor of ``out_dir`` lives.
    An unrelated repository or a plain folder gives None: a scratch folder.
    """
    if out_dir == root or root in out_dir.parents:
        return root
    ancestor = next((path for path in (out_dir, *out_dir.parents) if path.is_dir()), None)
    top = _git_path(ancestor, "--show-toplevel") if ancestor else None
    if ancestor is None or top is None:
        return None
    common = _git_path(ancestor, "--git-common-dir")
    return top if common is not None and common == _git_path(root, "--git-common-dir") else None


def _gate_target(root: Path, out_dir: Path) -> Path | None:
    """The work tree to gate on, or None for a scratch folder. In a work tree, ``out_dir``
    must be one of its located ADR folders."""
    tree = _gate_tree(root, out_dir)
    if tree is not None:
        allowed = {
            (tree / rel).resolve() for rel, _source in locate_folders(tree) if is_draft_target(rel)
        }
        if out_dir not in allowed:
            raise ConfigError(
                f"{out_dir} is inside the repository {tree} and is not an ADR folder that takes drafts"
            )
    return tree


def _refuse_ignored(root: Path, target: Path) -> None:
    proc = git_text(
        root, "check-ignore", "-q", "--", target.relative_to(root).as_posix(), ok=(0, 1)
    )
    if proc.returncode == 0:
        raise ConfigError(f"{target} is ignored by git; the ADR would not be committed")


def _file_name(style: Style, number: int, candidate: dict[str, Any]) -> str:
    slug = slugify(candidate["title"])
    if not slug:
        source = candidate.get("source")
        sha = source.get("sha") if isinstance(source, dict) else None
        base = f"decision-{sha[:7]}" if isinstance(sha, str) and sha else None
        slug = base or f"decision-{slugify(str(candidate['id'])) or 'unnamed'}"
    return f"{style.prefix}{number:0{style.width}d}-{slug}.md"


def draft(scan_path: str, ident: str, out: str, status: str) -> dict[str, Any]:
    """Write one ADR for candidate ``ident`` into ``out`` and return the ``draft`` payload."""
    if not _STATUS.fullmatch(status):
        raise ConfigError(f"--status {status!r} must be a short plain word or phrase")
    scan, candidate = load_candidate(scan_path, ident)
    _check_candidate(candidate)
    root = repo_root(Path(scan["repo"]))
    out_dir = Path(out).resolve()
    tree = _gate_target(root, out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"--out {out_dir} is not a directory")
    out_dir.mkdir(parents=True, exist_ok=True)
    style = folder_style(out_dir)
    number = style.highest + 1
    target = out_dir / _file_name(style, number, candidate)
    if tree is not None:
        _refuse_ignored(tree, target)
    text = render(style, number, candidate, status)
    try:
        with open(target, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise ExistsError(f"{target} already exists; it is never replaced", target) from exc
    twins = [
        item.name
        for item in adr_files(out_dir)
        if item.number == number and item.name != target.name
    ]
    if twins:
        raise ExistsError(f"another ADR took number {number}", target, twins)
    return {
        "path": str(target),
        "number": number,
        "id": ident,
        "status": status,
        "in_repo": tree is not None,
    }
