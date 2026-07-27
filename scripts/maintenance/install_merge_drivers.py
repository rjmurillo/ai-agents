"""Register this repository's git merge drivers in the local clone.

A ``.gitattributes`` entry naming a merge driver does nothing on its own. Git
looks the name up in config, and config is per clone and never committed, so a
clone without the matching ``git config`` silently falls back to the default
text merge. For the causal graph that means the conflict this repository is
trying to eliminate comes back, and the developer resolving it by hand deletes
graph state without knowing (issue #3345).

Running this from the pre-commit hook makes a clone self-heal on its first
commit instead of depending on a setup step someone can skip. It is idempotent:
if the driver is already registered with the value we want, nothing is written.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _interpreter() -> str:
    """Return the interpreter to bake into the registered driver command.

    A bare, PATH-resolved name (``python3``, falling back to ``python``), never
    this process's absolute ``sys.executable``. The merge driver needs no
    project environment (it imports only the standard library), so any Python
    >=3.10 on PATH runs it, and a bare name is the only form that stays correct
    across git worktrees. The 3.10 floor is real: the driver imports
    ``typing.TypeAlias`` and evaluates a PEP 604 ``X | Y`` union at import time,
    both of which raise on 3.9. Baking a bare name trades one worktree's pinned
    interpreter for the clone's PATH, which is the contract issue #3418 asks
    for; a merge-time PATH without a >=3.10 python is out of that scope.

    Linked worktrees share one ``.git/config``, so the first worktree to run the
    installer would register its own absolute venv path for all of them. When
    that worktree or its venv is later deleted, the baked path stops resolving,
    the driver exits 127, and git falls back to the text merge, silently
    reintroducing the conflict the driver exists to remove (issue #3418). A bare
    name cannot point at a deleted directory, so it survives the shared config.

    A name also survives ``sh``: git hands the driver string to ``sh`` even on
    Windows, and ``sh`` eats the backslashes in a native ``D:\\...\\python.exe``.
    A bare name has none. ``python3`` is preferred; some Windows installs expose
    only ``python``. If neither resolves, ``python3`` is the last literal left.
    """
    for name in ("python3", "python"):
        if shutil.which(name):
            return name
    return "python3"


# driver name -> (config key suffix, value)
_DRIVERS: dict[str, dict[str, str]] = {
    "causal-graph": {
        "name": "Union merge for the generated causal graph",
        # Git runs a merge driver from the top of the working tree even when
        # `git merge` was invoked in a subdirectory, so the relative script path
        # resolves. Verified by probe; see PR #3348.
        #
        # %O %A %B are quoted as a matter of shell hygiene. Git substitutes them
        # into this string before sh parses it, and today it substitutes bare
        # temp names like .merge_file_yvRBP2 that cannot contain a space.
        #
        # A bare, PATH-resolved interpreter name rather than `uv run --frozen
        # python` or an absolute venv path. The driver imports only argparse,
        # json, sys, pathlib and typing, so it needs no project environment
        # (any Python >=3.10 on PATH runs it), and routing it through uv would
        # let a merge fail wherever uv cannot run: offline, before the first
        # sync, or in a clone that never installed it. A failed driver is not a
        # loud error, it is a silent fall back to the text merge and the
        # conflict this driver exists to eliminate.
        #
        # The name (not an absolute path) is what keeps this correct across git
        # worktrees. Linked worktrees share one `.git/config`, so an absolute
        # venv path baked by one worktree breaks every other worktree the moment
        # that venv is relocated or deleted (issue #3418). A bare name resolves
        # against PATH at merge time and cannot dangle. It is written to
        # `git config --local`, never committed, and re-registered from
        # pre-commit whenever the computed value differs.
        "driver": (f'"{_interpreter()}" scripts/validation/merge_causal_graph.py "%O" "%A" "%B"'),
    },
}


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _current(key: str) -> str | None:
    result = _git(["config", "--local", "--get", key])
    return result.stdout.strip() if result.returncode == 0 else None


def install() -> int:
    """Return 0 when every driver is registered, 1 when git rejected a write."""
    for driver, settings in _DRIVERS.items():
        for setting, value in settings.items():
            key = f"merge.{driver}.{setting}"
            if _current(key) == value:
                continue
            result = _git(["config", "--local", key, value])
            if result.returncode != 0:
                print(
                    f"ERROR: could not set {key}: {result.stderr.strip()}",
                    file=sys.stderr,
                )
                # ADR-035: a failed `git config` write is a configuration
                # failure (2), not a logic error (1).
                return 2
            print(f"Registered merge driver setting {key}")
    return 0


if __name__ == "__main__":
    sys.exit(install())
