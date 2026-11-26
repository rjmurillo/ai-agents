"""Build a Windows command for a bare program name, such as ``az`` (``az.cmd``).

Without a shell, CreateProcess finds only ``.exe`` files, so ``run`` resolves
the name here. The lookup reads absolute ``PATH`` entries only, never the
current directory, so a checked-in ``az.cmd`` cannot stand in for the CLI.

A ``.cmd`` or ``.bat`` target runs through cmd.exe, which re-parses the
command line. Every argument is then double-quoted, which keeps ``&``, ``|``,
``<``, ``>``, and ``^`` literal. cmd.exe still expands ``%`` and ``!`` inside
quotes, so an argument holding one of those, a quote, a line break, or a
trailing backslash is refused rather than rewritten.
"""

from __future__ import annotations

import os
import re

BATCH_SUFFIXES = (".cmd", ".bat")
_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"
_BATCH_UNSAFE = re.compile(r'[%!"\r\n]|\\\Z')


def find_program(name: str) -> str | None:
    """Return the first absolute PATH entry holding ``name`` with a PATHEXT suffix."""
    suffixes = [s for s in (os.environ.get("PATHEXT") or _DEFAULT_PATHEXT).split(";") if s]
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
    if os.name != "nt" or os.path.dirname(argv[0]):
        return argv
    found = find_program(argv[0])
    if found is None:
        return argv
    if not found.lower().endswith(BATCH_SUFFIXES):
        return [found, *argv[1:]]
    if any(_BATCH_UNSAFE.search(arg) for arg in argv[1:]):
        return None
    return " ".join(f'"{part}"' for part in [found, *argv[1:]])
