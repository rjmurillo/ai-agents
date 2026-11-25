"""The one git runner for adr_drift.py: argument lists, no shell, a timeout, no prompts.

python3, stdlib only, no network.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

GIT_TIMEOUT_SECONDS = 120
# The variables `git rev-parse --local-env-vars` lists, plus the namespace and discovery
# ceiling. Inherited, any of them points git at another repository whatever `-C` says.
# skill-bootstrap's adr_scan.py strips the same set.
LOCAL_GIT_ENV = frozenset(
    "GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CEILING_DIRECTORIES GIT_COMMON_DIR GIT_CONFIG "
    "GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_DIR "
    "GIT_GRAFT_FILE GIT_IMPLICIT_WORK_TREE GIT_INDEX_FILE GIT_NAMESPACE GIT_NO_REPLACE_OBJECTS "
    "GIT_OBJECT_DIRECTORY GIT_PREFIX GIT_REPLACE_REF_BASE GIT_SHALLOW_FILE GIT_WORK_TREE".split()
)


class GitError(Exception):
    """A git command failed, timed out, or could not run.

    `returncode` is git's exit status when it ran and failed, else None.
    `timed_out` is True when the command hit GIT_TIMEOUT_SECONDS.
    """

    def __init__(
        self, message: str, returncode: int | None = None, timed_out: bool = False
    ) -> None:
        super().__init__(message)
        self._returncode = returncode
        self._timed_out = timed_out

    @property
    def returncode(self) -> int | None:
        return self._returncode

    @property
    def timed_out(self) -> bool:
        return self._timed_out


def run_git(repo: Path, args: Sequence[str]) -> str:
    """Run `git -C repo ARGS` with an argument list and return stdout."""
    argv = ["git", "-C", str(repo), "-c", "core.quotepath=off", *args]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=_git_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(
            f"git {args[0] if args else ''} timed out after {GIT_TIMEOUT_SECONDS} s", timed_out=True
        ) from exc
    except OSError as exc:
        raise GitError(f"git {args[0] if args else ''} could not run: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-1:] or ["no stderr"]
        raise GitError(
            f"git {args[0] if args else ''} exited {proc.returncode}: {tail[0]}", proc.returncode
        )
    return proc.stdout


def _git_env() -> dict[str, str]:
    """No repository redirection, no prompt, no lock writes, and no replacement objects."""
    env = {key: value for key, value in os.environ.items() if key not in LOCAL_GIT_ENV}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    return env
