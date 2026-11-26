"""Build a Windows command for a bare program name, such as ``az`` (``az.cmd``).

Without a shell, CreateProcess finds only ``.exe`` files, so ``run`` resolves
the name here. The lookup reads absolute ``PATH`` entries only, never the
current directory, so a checked-in ``az.cmd`` cannot stand in for the CLI.

A ``.cmd`` or ``.bat`` target runs through cmd.exe, which re-parses the
command line. Every argument is then double-quoted, which keeps ``&``, ``|``,
``<``, ``>``, and ``^`` literal. cmd.exe still expands ``%`` inside quotes,
and ``!`` when delayed expansion is on, so an argument holding one of those,
a quote, a line break, or a trailing backslash is refused rather than
rewritten. ``cmd_rewrites`` lets a caller refuse it before any push.

CreateProcess also searches the current directory before ``PATH`` for a bare
name, so a ``git.exe`` committed at the checkout root would run in place of
git when a helper runs there. ``planted_programs`` finds those files so the
caller can refuse the checkout (CWE-427).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

BATCH_SUFFIXES = (".cmd", ".bat")
# The programs the ship scripts spawn by bare name.
SPAWNED_PROGRAMS = ("git", "gh", "az")
_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"
_BATCH_UNSAFE = re.compile(r'[%!"\r\n]|\\\Z')


def on_windows() -> bool:
    """Return whether this host is Windows; one seam for the callers and tests."""
    return os.name == "nt"


def cmd_rewrites(arg: str) -> bool:
    """Return whether cmd.exe could rewrite ``arg`` inside double quotes."""
    return _BATCH_UNSAFE.search(arg) is not None


def _pathext_suffixes() -> list[str]:
    return [s for s in (os.environ.get("PATHEXT") or _DEFAULT_PATHEXT).split(";") if s]


def planted_programs(root: Path) -> list[str]:
    """Return the files in ``root`` named like a spawned program plus a PATHEXT suffix.

    Each entry is ``<name><suffix>``, such as ``git.EXE``, for a name in
    ``SPAWNED_PROGRAMS``. An empty list means the root holds none.
    """
    return [
        name + suffix
        for name in SPAWNED_PROGRAMS
        for suffix in _pathext_suffixes()
        if (root / (name + suffix)).is_file()
    ]


def find_program(name: str) -> str | None:
    """Return the first absolute PATH entry holding ``name`` with a PATHEXT suffix."""
    suffixes = _pathext_suffixes()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        for suffix in suffixes:
            candidate = os.path.join(entry, name + suffix)
            if os.path.isfile(candidate):
                return candidate
    return None


def command(argv: list[str]) -> list[str] | str | None:
    """Return what to pass to ``subprocess.run``, or None when cmd.exe would rewrite it.

    Off Windows, and for a name with a directory part, ``argv`` is unchanged.
    An unfound name is also unchanged, so the call reads as not found (127).
    """
    if not on_windows() or os.path.dirname(argv[0]):
        return argv
    found = find_program(argv[0])
    if found is None:
        return argv
    if not found.lower().endswith(BATCH_SUFFIXES):
        return [found, *argv[1:]]
    if any(cmd_rewrites(arg) for arg in argv[1:]):
        return None
    return " ".join(f'"{part}"' for part in [found, *argv[1:]])
