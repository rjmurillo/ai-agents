"""The one git runner for adr_drift.py: argument lists, no shell, a timeout, no prompts.

python3, stdlib only, no network.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

GIT_TIMEOUT_SECONDS = 120


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
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env
