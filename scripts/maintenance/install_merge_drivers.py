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

import argparse
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
_CAUSAL_GRAPH_DRIVER = Path("scripts/validation/merge_causal_graph.py")
_TRUSTED_COPY_DIR = Path("ai-agents-merge-drivers")


def _driver_command(script_path: Path = _CAUSAL_GRAPH_DRIVER) -> str:
    return f'"{_interpreter()}" "{script_path.as_posix()}" "%O" "%A" "%B"'


def _drivers(script_path: Path = _CAUSAL_GRAPH_DRIVER) -> dict[str, dict[str, str]]:
    return {
        "causal-graph": {
            "name": "Union merge for the generated causal graph",
            # Git runs a merge driver from the top of the working tree even when
            # `git merge` was invoked in a subdirectory, so the relative script
            # path resolves. Verified by probe; see PR #3348.
            #
            # %O %A %B are quoted as a matter of shell hygiene. Git substitutes
            # them into this string before sh parses it, and today it
            # substitutes bare temp names like .merge_file_yvRBP2 that cannot
            # contain a space.
            #
            # A bare, PATH-resolved interpreter name rather than `uv run
            # --frozen python` or an absolute venv path. The driver imports
            # the standard library only, so it needs no project environment
            # (any Python >=3.10 on PATH runs it), and
            # routing it through uv would let a merge fail wherever uv cannot
            # run: offline, before the first sync, or in a clone that never
            # installed it. A failed driver is not a loud error, it is a silent
            # fall back to the text merge and the conflict this driver exists
            # to eliminate.
            #
            # The default relative script path keeps local worktrees correct.
            # Linked worktrees share one `.git/config`, so an absolute venv path
            # baked by one worktree breaks every other worktree the moment that
            # venv is relocated or deleted (issue #3418). CI callers that hold
            # secrets use install_trusted_copy() instead, which registers a copy
            # under the git common dir before checking out PR-controlled code.
            "driver": _driver_command(script_path),
        },
    }


_DRIVERS: dict[str, dict[str, str]] = _drivers()


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


def install(script_path: Path = _CAUSAL_GRAPH_DRIVER) -> int:
    """Return 0 when every driver is registered, 2 when git rejected a write."""
    for driver, settings in _drivers(script_path).items():
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


def _git_common_dir() -> Path:
    result = _git(["rev-parse", "--git-common-dir"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "could not resolve git common dir")
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = (_PROJECT_ROOT / common_dir).resolve()
    return common_dir


def install_trusted_copy() -> int:
    """Register a driver copy outside the working tree for secret-bearing CI."""
    try:
        trusted_dir = _git_common_dir() / _TRUSTED_COPY_DIR
        trusted_dir.mkdir(parents=True, exist_ok=True)
        source = _PROJECT_ROOT / _CAUSAL_GRAPH_DRIVER
        target = trusted_dir / _CAUSAL_GRAPH_DRIVER.name
        shutil.copy2(source, target)
    except OSError as exc:
        print(f"ERROR: could not prepare trusted merge driver copy: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return install(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trusted-copy",
        action="store_true",
        help="Copy drivers under the git common dir before registering them.",
    )
    args = parser.parse_args(argv)
    if args.trusted_copy:
        return install_trusted_copy()
    return install()


if __name__ == "__main__":
    sys.exit(main())
