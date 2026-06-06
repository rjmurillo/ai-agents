"""Canonical: scripts/github_core/worktree_identity.py. Sync via scripts/sync_plugin_lib.py.

Pins a known-good operator identity into a git worktree's local config,
clobbering any leaked placeholder identity that may have been written by
a pytest fixture running with the wrong cwd.

WHY: pytest fixtures in this repo call ``git config user.email ...`` with
``cwd=tmp_path``. When the cwd accidentally resolves to or inside a
pr-autofix worktree, the placeholder ``test@test.com`` gets written into
the worktree's local .git/config. Any commits produced in that worktree
then carry the placeholder identity, which GitHub assembles into squash
trailer blocks (issue #2466, commit a2cc80e7, PR #2458).

Usage:
    from .worktree_identity import reset_worktree_identity

    reset_worktree_identity(worktree_path, operator="rjmurillo-bot")
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_BOT_NAME = "rjmurillo-bot"
_BOT_EMAIL = "rjmurillo-bot@users.noreply.github.com"


def _run_git_config(
    args: list[str],
    cwd: Path,
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    return subprocess.run(
        ["git", "-C", str(cwd), "config", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=check,
    )


def reset_worktree_identity(
    worktree_path: str | Path,
    *,
    operator: str = "rjmurillo-bot",
) -> None:
    """Clobber any local user.name/user.email and pin the operator identity.

    Steps performed in order:
    1. ``git -C <worktree> config --local --unset-all user.name``  (best-effort)
    2. ``git -C <worktree> config --local --unset-all user.email``  (best-effort)
    3. If operator == "rjmurillo-bot": set local user.name and user.email to
       the bot identity so all commits in the worktree are attributed correctly.
    4. If operator == "rjmurillo": leave local config unset, so the human's
       global ~/.gitconfig identity flows through.

    Args:
        worktree_path: Path to the git worktree directory.
        operator:      "rjmurillo-bot" (default, for CI/bot runs) or
                       "rjmurillo" (for human-run invocations where the
                       global identity should flow through).
    """
    path = Path(worktree_path)

    # Step 1-2: best-effort unset (exit code 5 = key not found, which is fine)
    _run_git_config(["--local", "--unset-all", "user.name"], path)
    _run_git_config(["--local", "--unset-all", "user.email"], path)

    if operator == "rjmurillo-bot":
        # Step 3: pin bot identity
        _run_git_config(["--local", "user.name", _BOT_NAME], path, check=True)
        _run_git_config(["--local", "user.email", _BOT_EMAIL], path, check=True)
    # else operator == "rjmurillo": leave unset (step 4 is a no-op)
