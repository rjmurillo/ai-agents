"""Run one shipped plugin script from its path relative to the plugin root (ADR-121).

The shell locator in a shipped command picks the plugin root that holds this
file, then runs it as ``python3 <root>/lib/ptk_run.py skills/NAME/scripts/FILE.py ARGS``.
This module validates the target, joins it to its own plugin root, and runs it.

* ``argv[1]`` is the target, relative to the plugin root (the directory that
  holds ``lib/``). The remaining arguments belong to the target.
* The root is computed from this file's path, lexically. A symlinked
  ``.claude/lib/ptk_run.py`` therefore resolves to ``.claude``, not ``src/claude``.
* When the target is not under this root, the later locator candidates are
  tried in order: ``CLAUDE_PLUGIN_ROOT``, ``COPILOT_PLUGIN_ROOT``, then
  ``.claude`` under the working directory (ADR-121 decision 11). A candidate
  must hold this resolver and the target. One that names the same tree as this
  root or an earlier candidate (by ``os.path.realpath``) is skipped. A fallthrough
  writes one ``ptk_run: note:`` line to stderr and leaves stdout to the target.
* On POSIX the target replaces this process (``os.execv``), so its exit code and
  ``sys.path[0]`` match a direct ``python3 <file>``. Elsewhere ``os.execv``
  returns to the shell at once, so the target runs as a child and its exit code
  is passed on. Under ``python3 -I`` the target also runs with ``-I`` (ADR-121
  decision 12), on both paths.
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
NOTE_PREFIX = "ptk_run: note:"
RESOLVER_REL = os.path.join("lib", "ptk_run.py")
# The locator's candidate order after the host-rewritten token (ADR-121 decision 3).
FALLTHROUGH_ENV_VARS = ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")
FALLBACK_ROOT = ".claude"
USAGE = "usage: ptk_run.py skills/NAME/scripts/FILE.py [ARGS...]"

# Same pattern as build/scripts/copilot_launcher.py (_SCRIPT_REL_RE) and
# build/scripts/plugin_run_launcher.py; a conformance test pins all three.
# The class excludes NUL, backslash, quotes, `$`, and whitespace. A leading `/`
# cannot match because the pattern starts with `skills/`.
TARGET_RE = re.compile(r"skills/[A-Za-z0-9_./-]+\.py")
# A part of two or more dots. ``..`` climbs a directory, and Windows can read a longer
# run of dots as a parent reference too. A single ``.`` is harmless and stays allowed.
DOTS_ONLY_RE = re.compile(r"\.{2,}")


class ResolverError(Exception):
    """The target cannot be run. The message is printed after ``ptk_run:``."""


def plugin_root() -> str:
    """Return the directory that holds the ``lib/`` directory this file sits in."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def validate_target(target: str) -> None:
    """Raise :class:`ResolverError` unless ``target`` is a plugin script path."""
    if not TARGET_RE.fullmatch(target):
        raise ResolverError(f"target is not skills/<path>.py: {target!r}")
    if any(DOTS_ONLY_RE.fullmatch(part) for part in target.split("/")):
        raise ResolverError(f"target has a part made only of dots: {target!r}")


def candidate_roots(own_root: str) -> list[str]:
    """Return the fallthrough roots in locator order, minus empties and repeats.

    ``realpath`` only decides whether two spellings name one tree, so an ADR-119
    link back to this root is not probed twice. The target test stays lexical.
    """
    raw = [os.environ.get(name, "") for name in FALLTHROUGH_ENV_VARS] + [FALLBACK_ROOT]
    seen = {os.path.realpath(own_root)}
    roots: list[str] = []
    for root in raw:
        if not root:
            continue
        real = os.path.realpath(root)
        if real in seen:
            continue
        seen.add(real)
        roots.append(root)
    return roots


def _holds(root: str, target: str) -> bool:
    return os.path.isfile(os.path.join(root, RESOLVER_REL)) and os.path.isfile(
        os.path.join(root, target)
    )


def resolve_target(root: str, target: str) -> str:
    """Return the path of ``target`` under ``root`` or a later candidate root.

    The check is lexical. ``os.path.isfile`` follows a link to a file, which the
    ADR-119 dogfood tree needs, and a link to a directory fails. The own root wins
    whenever it holds the target. Raises :class:`ResolverError` when no root does.
    """
    validate_target(target)
    path = os.path.join(root, target)
    if os.path.isfile(path):
        return path
    for candidate in candidate_roots(root):
        if _holds(candidate, target):
            print(
                f"{NOTE_PREFIX} {target!r} is not under {root!r}; running it from {candidate!r}",
                file=sys.stderr,
            )
            return os.path.join(candidate, target)
    raise ResolverError(f"target is not a file under any plugin root: {target!r}")


def interpreter_flags() -> list[str]:
    """Return the flags this interpreter carries that the target must share.

    Under ``python3 -I`` the target also gets ``-I``, so the run matches a direct
    ``python3 -I <file>`` (ADR-121 decision 12).
    """
    return ["-I"] if sys.flags.isolated else []


def _launch(path: str, args: list[str]) -> int:
    """Run ``path`` with the current interpreter. Returns only off POSIX."""
    if not sys.executable:
        raise ResolverError("sys.executable is empty, so the interpreter cannot be reused")
    command = [sys.executable, *interpreter_flags(), path, *args]
    # Both calls take an argv list with no shell. resolve_target admits only a
    # skills/<path>.py target under a root that holds lib/ptk_run.py, and this
    # is not an auth boundary (ADR-121 decision 10). Owner ruling: issue #7591.
    if IS_POSIX:
        # nosemgrep: python.lang.security.audit.dangerous-os-exec-tainted-env-args.dangerous-os-exec-tainted-env-args  # noqa: E501
        os.execv(sys.executable, command)
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args  # noqa: E501
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
