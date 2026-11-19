"""Inbound links broken by a rename, a deletion, or a removed heading.

File arguments scan the named pages. A rename breaks links in pages that were
not named. This module reads ``git diff --name-status -M`` and returns the
extra in-scope pages a basename search finds. The staged diff wins. When
nothing is staged, the diff is ``base...HEAD``.
"""

from __future__ import annotations

import posixpath
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from check_adr_links import _run_git, is_adr_target, resolve_base_ref
from md_anchors import anchors_in
from md_link_parse import EXTERNAL_SCHEME_RE, split_destination_fragment


@dataclass(frozen=True)
class InboundScan:
    """Removed paths, anchors dropped from modified files, and pages to scan."""

    removed: frozenset[str]
    dropped: dict[str, frozenset[str]]
    files: tuple[str, ...]


def _parse_name_status(blob: str) -> list[tuple[str, str, str | None]]:
    """Parse ``git diff --name-status -z`` records, including rename pairs."""
    parts = blob.split("\0")
    rows: list[tuple[str, str, str | None]] = []
    index = 0
    while index < len(parts) and parts[index]:
        status = parts[index]
        if status[0] in "RC":
            if index + 2 >= len(parts):
                break
            rows.append((status, parts[index + 1], parts[index + 2]))
            index += 3
            continue
        if index + 1 >= len(parts):
            break
        rows.append((status, parts[index + 1], None))
        index += 2
    return rows


def _records(repo: Path, diff_args: list[str]) -> list[tuple[str, str, str | None]] | None:
    result = _run_git(repo, ["diff", "--name-status", "-M", "-z", *diff_args])
    if result.returncode != 0:
        return None
    return _parse_name_status(result.stdout)


def _show(repo: Path, spec: str) -> str | None:
    result = _run_git(repo, ["show", spec])
    if result.returncode != 0:
        return None
    return result.stdout


def _outside(path: str) -> bool:
    if not path or path.startswith("/") or EXTERNAL_SCHEME_RE.match(path):
        return True
    return bool(is_adr_target(path))


def _dropped_anchors(
    repo: Path, records: list[tuple[str, str, str | None]], old_prefix: str, new_prefix: str
) -> dict[str, frozenset[str]]:
    dropped: dict[str, frozenset[str]] = {}
    for status, path, new_path in records:
        current = new_path if status[0] in "RC" else path
        if current is None or status[0] not in "MRC":
            continue
        if not current.endswith(".md") or not path.endswith(".md"):
            continue
        old = _show(repo, f"{old_prefix}{path}")
        new = _show(repo, f"{new_prefix}{current}")
        if old is None or new is None:
            continue
        gone = frozenset(anchors_in(old) - anchors_in(new))
        if gone:
            dropped[current] = gone
    return dropped


def _mentions(
    repo: Path, needles: list[str], already: set[str], scope: Callable[[str], bool]
) -> tuple[str, ...]:
    """Return in-scope pages whose text contains an old basename."""
    if not needles:
        return ()
    args = ["grep", "-F", "-I", "-l", "-z"]
    for needle in needles:
        args.extend(("-e", needle))
    result = _run_git(repo, args)
    if result.returncode not in (0, 1):
        return ()
    found: set[str] = set()
    for name in result.stdout.split("\0"):
        if not name:
            continue
        name = name.replace("\\", "/")
        if name in already or not scope(name):
            continue
        found.add(name)
    return tuple(sorted(found))


def collect_inbound(
    repo: Path, base_ref: str | None, already: set[str], scope: Callable[[str], bool]
) -> InboundScan:
    """Return the inbound scan for a file-argument run. ``scope`` is ``in_scope``."""
    staged = _records(repo, ["--cached"])
    if staged:
        records = staged
        old_prefix, new_prefix = "HEAD:", ":"
    else:
        resolved = resolve_base_ref(repo) if base_ref == "auto" else base_ref
        committed = (
            _records(repo, [f"{resolved}...HEAD"])
            if resolved and resolved not in ("none", "auto")
            else None
        )
        records = committed or []
        old_prefix, new_prefix = f"{resolved}:", "HEAD:"
    removed = frozenset(
        path.replace("\\", "/") for status, path, _new in records if status[0] in "RD"
    )
    dropped = _dropped_anchors(repo, records, old_prefix, new_prefix)
    needles: list[str] = []
    seen: set[str] = set()
    for path in (*removed, *dropped):
        name = posixpath.basename(path)
        if name and name not in seen:
            seen.add(name)
            needles.append(name)
    return InboundScan(removed, dropped, _mentions(repo, needles, already, scope))


def inbound_kept(
    kind: str,
    file: str,
    target: str,
    removed: frozenset[str],
    dropped: dict[str, frozenset[str]],
    known: Callable[[str], bool],
    follow: Callable[[str], str],
) -> bool:
    """Return whether one finding was caused by a removed path or heading."""
    raw_path, fragment = split_destination_fragment(target)
    path = unquote(raw_path.split("?", 1)[0])
    if _outside(path):
        return False
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(file), path))
    escaped = resolved == ".." or resolved.startswith("../")
    followed = follow(resolved) if not escaped and not known(resolved) else resolved
    if kind == "missing-target":
        return resolved in removed or followed in removed
    if kind == "missing-anchor":
        return unquote(fragment) in dropped.get(followed, ())
    return False
