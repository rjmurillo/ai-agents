"""Scoped git ``safe.directory`` trust for mutation workspace git calls."""

from __future__ import annotations

import os
from pathlib import Path

# nektos/act sets ACT=true in every job container; run_workflow_local_test.py
# reads the same marker. GitHub-hosted runners and developer shells do not set it.
ACT_MARKER_ENV = "ACT"


def safe_directory_args(repo_root: Path) -> list[str]:
    """Trust ``repo_root`` for one git call, and only inside an act container.

    act copies the worktree into the job container, where git runs as a
    different UID than the files' owner, so git refuses it with "detected
    dubious ownership" (every mutation harness failed this way from a linked
    worktree). ``run_git`` pins ``GIT_CONFIG_GLOBAL`` and the system config to
    ``os.devnull``, so a ``safe.directory`` entry in either never reaches git;
    ``-c`` is the one channel git honors for it.

    Stricter than a global trust: one path (the resolved root the call was
    given), no ``*``, no persisted config. Outside act the list is empty, so a
    host or CI checkout with a dubious owner is still refused.
    """
    if os.environ.get(ACT_MARKER_ENV, "").strip().lower() != "true":
        return []
    return ["-c", f"safe.directory={repo_root.resolve()}"]
