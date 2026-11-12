"""Run one shipped plugin script from its path relative to the plugin root (ADR-121).

The shell locator in a shipped command picks the plugin root that holds this
file, then runs it as ``python3 <root>/lib/ptk_run.py skills/NAME/scripts/FILE.py ARGS``.
This module validates the target, joins it to its own plugin root, and runs it.

* ``argv[1]`` is the target, relative to the plugin root (the directory that
  holds ``lib/``). The remaining arguments belong to the target.
* The root is computed from this file's path, lexically. A symlinked
  ``.claude/lib/ptk_run.py`` therefore resolves to ``.claude``, not ``src/claude``.
* On POSIX the target replaces this process (``os.execv``), so its exit code and
  ``sys.path[0]`` match a direct ``python3 <file>``. Elsewhere ``os.execv``
  returns to the shell at once, so the target runs as a child and its exit code
  is passed on.
* Every resolver failure writes one line that starts with ``ptk_run:`` to stderr
  and exits 2 (ADR-035 config error). A target's own exit 2 carries no such
  prefix, so callers tell the two apart by it.

Stdlib only at import time: the locator runs this file under a bare ``python3``.

Not an authentication boundary (ADR-121 decision 10). Any root that holds this
file passes the locator's probe, and whoever controls a root controls every file
under it, so the target check is lexical and does not resolve symlinks.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

IS_POSIX = os.name == "posix"
EXIT_CONFIG_ERROR = 2
ERROR_PREFIX = "ptk_run:"
USAGE = "usage: ptk_run.py skills/NAME/scripts/FILE.py [ARGS...]"

# Same pattern as build/scripts/copilot_launcher.py (_SCRIPT_REL_RE) and
# build/scripts/plugin_run_launcher.py; a conformance test pins all three.
# The class excludes NUL, backslash, quotes, `$`, and whitespace. A leading `/`
# cannot match because the pattern starts with `skills/`.
TARGET_RE = re.compile(r"skills/[A-Za-z0-9_./-]+\.py")


class ResolverError(Exception):
    """The target cannot be run. The message is printed after ``ptk_run:``."""


def plugin_root() -> str:
    """Return the directory that holds the ``lib/`` directory this file sits in."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def validate_target(target: str) -> None:
    """Raise :class:`ResolverError` unless ``target`` is a plugin script path."""
    if not TARGET_RE.fullmatch(target):
        raise ResolverError(f"target is not skills/<path>.py: {target!r}")
    if ".." in target.split("/"):
        raise ResolverError(f"target has a '..' part: {target!r}")


def resolve_target(root: str, target: str) -> str:
    """Return the path of ``target`` under ``root``; raise unless it is a file.

    The check is lexical. ``os.path.isfile`` follows a link to a file, which the
    ADR-119 dogfood tree needs, and a link to a directory fails.
    """
    validate_target(target)
    path = os.path.join(root, target)
    if not os.path.isfile(path):
        raise ResolverError(f"target is not a file: {path}")
    return path


def _launch(path: str, args: list[str]) -> int:
    """Run ``path`` with the current interpreter. Returns only off POSIX."""
    command = [sys.executable, path, *args]
    if IS_POSIX:
        os.execv(sys.executable, command)
    return subprocess.run(command, check=False).returncode


def main(argv: list[str]) -> int:
    """Validate ``argv[1]``, run it with ``argv[2:]``, and return the exit code."""
    if len(argv) < 2:
        print(f"{ERROR_PREFIX} {USAGE}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    try:
        path = resolve_target(plugin_root(), argv[1])
        return _launch(path, argv[2:])
    except (ResolverError, OSError) as exc:
        print(f"{ERROR_PREFIX} {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv))
