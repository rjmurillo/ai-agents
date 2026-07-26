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

import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _interpreter() -> str:
    """Return the interpreter to bake into the registered driver command.

    The merge driver is stdlib-only, so any Python that can start will run it.
    Registering this process's own interpreter is therefore both sufficient and
    the one path proven to work: it is running right now.

    ``as_posix`` matters because git hands the driver string to ``sh`` even on
    Windows, and ``sh`` eats the backslashes in a native ``D:\\...\\python.exe``.

    ``sys.executable`` is documented as possibly empty when the interpreter
    cannot determine its own path (embedded hosts). ``python3`` is the only
    fallback left at that point.
    """
    return Path(sys.executable).as_posix() if sys.executable else "python3"


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
        # An absolute interpreter path rather than `uv run --frozen python`.
        # The driver imports only argparse, json, sys, pathlib and typing, so it
        # needs no project environment, and routing it through uv would let a
        # merge fail wherever uv cannot run: offline, before the first sync, or
        # in a clone that never installed it. A failed driver is not a loud
        # error, it is a silent fall back to the text merge and the conflict
        # this driver exists to eliminate.
        #
        # The path is machine-local, which is the right scope: it is written to
        # `git config --local`, which is never committed. It self-heals because
        # the installer runs from pre-commit and rewrites the key whenever the
        # computed value differs from what is registered, so a recreated or
        # relocated venv is repaired on the next commit.
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
