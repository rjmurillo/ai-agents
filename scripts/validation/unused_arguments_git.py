"""Shared plumbing for ``check_unused_arguments.py``: errors, one deadline, git calls."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

KEY_SEPARATOR = ": "

# One deadline for the whole run. lefthook kills the python-unused-arguments
# job at 90s with no message, so the gate gives up first and says why. The
# per-call limits only bound a single hung call.
TOTAL_DEADLINE_SECONDS = 75.0
GIT_TIMEOUT_SECONDS = 30


class GateConfigError(RuntimeError):
    """Raised when the gate cannot trust its inputs."""


class ExternalToolError(RuntimeError):
    """Raised when a tool the gate runs does not finish in time."""


class Deadline:
    """One monotonic budget shared by every subprocess the gate starts."""

    def __init__(
        self, seconds: float = TOTAL_DEADLINE_SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._seconds = seconds
        self._clock = clock
        self._end = clock() + seconds

    def timeout_for(self, per_call: float, what: str) -> float:
        """Return the timeout for the next call, or raise when the budget is spent."""
        remaining = self._end - self._clock()
        if remaining <= 0:
            raise ExternalToolError(
                f"unused-argument gate: the {self._seconds:g}s total deadline ran out before {what}"
            )
        return min(per_call, remaining)

    @property
    def seconds(self) -> float:
        return self._seconds


# Same GIT_ filter as the sibling validators (check_unreachable_code.py,
# check_duplicate_test_helpers.py, check_subprocess_encoding.py, and others).
# A shared helper is a repo-wide change and is not part of this gate.
def clean_git_env() -> dict[str, str]:
    """Return the process environment without ambient Git repository pointers."""
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


def run_git(
    repo_root: Path, args: Sequence[str], deadline: Deadline
) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo_root`` under the shared deadline."""
    timeout = deadline.timeout_for(GIT_TIMEOUT_SECONDS, f"git {args[0]}")
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=clean_git_env(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(
            f"unused-argument gate: git {args[0]} timed out after {timeout:g}s"
        ) from exc
    except OSError as exc:
        raise GateConfigError(f"cannot run git: {exc}") from exc
