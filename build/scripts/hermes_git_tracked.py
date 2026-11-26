"""Which bytecode caches under a generated tree git does not track.

The Hermes stale-file scan uses this to skip caches a test run writes beside
shipped scripts, while a force-added ``.pyc`` still counts as stale output.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from binplace_manifest import is_bytecode_artifact

# Variables that point git at another tree or inject config. A hook can
# export them for its own repository; the listing must come from ``root``.
_GIT_REDIRECT_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
)


def _tracked_files(root: Path) -> set[str] | None:
    """Paths under ``root`` that git tracks, or None when git cannot say."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REDIRECT_VARS}
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "."],
            capture_output=True,
            check=True,
            timeout=60,
            env=env,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(
            f"Warning: git ls-files failed under {root}; caches count as stale: {exc}",
            file=sys.stderr,
        )
        return None
    return {os.fsdecode(p) for p in out.split(b"\0") if p}


def drop_untracked_caches(root: Path, files: set[str]) -> set[str]:
    """``files`` (relative to ``root``) without the bytecode caches git does not track.

    A tracked bytecode file is never planned output, so it stays: a
    force-added ``.pyc`` would run on import in a consumer's install. When
    git cannot list tracked files, every cache stays (fail closed).
    """
    tracked = _tracked_files(root)
    if tracked is None:
        return files
    return {f for f in files if f in tracked or not is_bytecode_artifact(Path(f))}
