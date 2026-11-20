"""Find rg and grep without trusting the working directory (issue #7493).

``shutil.which`` on Windows searches the current directory before ``PATH``, and
a relative ``PATH`` entry resolves against the cwd on every platform. Recall
runs with the cwd inside a repository the user just opened, so a planted
``rg.exe`` there would run on the next prompt. This resolver walks absolute
``PATH`` entries only and refuses any hit inside the repository or the cwd.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path

_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"


def _absolute_path_entries(path_value: str) -> list[Path]:
    """PATH entries that are absolute. Empty, ``.``, and relative entries are skipped."""
    entries: list[Path] = []
    for raw in path_value.split(os.pathsep):
        entry = raw.strip().strip('"')
        if not entry or entry == "." or not os.path.isabs(entry):
            continue
        entries.append(Path(entry))
    return entries


def _candidate_names(name: str, windows: bool, pathext: str) -> list[str]:
    if not windows:
        return [name]
    suffixes = [s for s in pathext.split(";") if s]
    return [name + suffix.lower() for suffix in suffixes] + [name + s for s in suffixes]


def _is_inside(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _resolved_roots(forbidden_roots: Iterable[Path | None]) -> list[Path]:
    roots: list[Path] = []
    for root in forbidden_roots:
        if root is None:
            continue
        try:
            roots.append(root.resolve())
        except OSError:
            continue
    return roots


def _cwd() -> Path | None:
    try:
        return Path.cwd()
    except OSError:
        return None


def resolve_tool(
    name: str,
    forbidden_roots: Iterable[Path | None] = (),
    *,
    path_value: str | None = None,
    pathext: str | None = None,
    windows: bool | None = None,
) -> str | None:
    """Return the first executable *name* on an absolute ``PATH`` entry, or None.

    A candidate whose resolved path is inside any of *forbidden_roots* or inside
    the current working directory is rejected, so a binary planted in the
    repository cannot be chosen even through an absolute ``PATH`` entry.
    ``path_value``, ``pathext`` and ``windows`` default to the process values.
    """
    is_windows = sys.platform == "win32" if windows is None else windows
    search_path = os.environ.get("PATH", "") if path_value is None else path_value
    extensions = os.environ.get("PATHEXT", _DEFAULT_PATHEXT) if pathext is None else pathext
    roots = _resolved_roots([*forbidden_roots, _cwd()])

    for entry in _absolute_path_entries(search_path):
        for candidate_name in _candidate_names(name, is_windows, extensions):
            candidate = entry / candidate_name
            if not (candidate.is_file() and os.access(candidate, os.X_OK)):
                continue
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if _is_inside(resolved, roots):
                continue
            return str(candidate)
    return None
