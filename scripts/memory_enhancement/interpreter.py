#!/usr/bin/env python3
"""Re-exec a memory hook under the project virtualenv when a dependency is missing.

``.claude/settings.json`` registers the memory hooks as ``python3 -u ...``,
matching every other hook in that file. Those other hooks are stdlib-only. The
recall and reflection hooks are not: they reach ``serena_integration``, which
imports ``frontmatter`` (pyproject.toml declares ``python-frontmatter``). On a
developer machine ``python3`` is the system interpreter, which does not carry
that package, so both hooks used to exit 0 having recalled nothing and written
nothing, which is the exact state issue #4011 reports.

Re-exec once under ``.venv`` so the registered command behaves the same as
``uv run``. Everything here is stdlib, so this module still imports under the
interpreter that is missing the dependency.

A consumer plugin install has no ``scripts/`` tree and no ``.venv``; there the
hooks keep failing open and this module is never reached.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REQUIRED_MODULE = "frontmatter"
REENTRY_GUARD = "MEMORY_HOOK_VENV_REEXEC"
VENV_DIRNAME = ".venv"

_INTERPRETER_NAMES = ("bin/python3", "bin/python", "Scripts/python.exe")


def dependency_available(module_name: str = REQUIRED_MODULE) -> bool:
    """True when the running interpreter can import module_name.

    Imports rather than probing ``importlib.util.find_spec`` so a package that
    is present but broken counts as unavailable, which is the condition the
    hooks actually care about.
    """
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True


def find_venv_interpreter(project_dir: Path) -> Path | None:
    """Interpreter inside ``project_dir/.venv``, or None when there is none."""
    venv_dir = project_dir / VENV_DIRNAME
    for relative in _INTERPRETER_NAMES:
        candidate = venv_dir / relative
        if candidate.is_file():
            return candidate
    return None


def running_under_venv(venv_dir: Path) -> bool:
    """True when the interpreter executing this call belongs to venv_dir.

    ``sys.prefix`` is the virtualenv root while a virtualenv is active and the
    base installation otherwise, so it separates the two cases directly.

    Comparing interpreter paths does not, which is what issue #4468 reports.
    A virtualenv's ``bin/python3`` is a symlink to the interpreter it was built
    from, so ``os.path.realpath`` collapses the virtualenv path and the running
    interpreter to the same file whenever both descend from that base install.
    That holds for the system ``python3`` the hooks actually run under, so the
    path comparison reported "already running here" for every invocation and
    the re-exec never happened.
    """
    try:
        return Path(sys.prefix).resolve() == venv_dir.resolve()
    except OSError:
        return False


def reexec_under_project_venv(
    project_dir: Path, argv: list[str] | None = None
) -> None:
    """Replace this process with the project venv interpreter when needed.

    Returns without doing anything when the dependency already imports, when
    the guard variable marks this process as the re-exec, when the project has
    no virtualenv, or when this process is already running under that
    virtualenv. The guard is set in ``os.environ`` before the exec so the child
    inherits it and a broken virtualenv cannot loop.
    """
    if os.environ.get(REENTRY_GUARD) == "1":
        return
    if dependency_available():
        return

    interpreter = find_venv_interpreter(project_dir)
    if interpreter is None:
        return
    if running_under_venv(project_dir / VENV_DIRNAME):
        return

    os.environ[REENTRY_GUARD] = "1"
    arguments = sys.argv if argv is None else argv
    os.execv(str(interpreter), [str(interpreter), "-u", *arguments])
