"""Shared plumbing for ``check_unused_arguments.py``: errors, one deadline, git calls."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from scripts.ci.count_ratchet import git_environment

KEY_SEPARATOR = ": "

# One deadline for the whole run. lefthook kills the python-unused-arguments
# job at 90s with no message, so the gate gives up first and says why, once the
# interpreter is running. The clock starts there: `uv run` environment setup
# before it counts against the 90s but not against this budget. The per-call
# limits only bound a single hung call.
TOTAL_DEADLINE_SECONDS = 75.0
GIT_TIMEOUT_SECONDS = 30
RUFF_VERSION_TIMEOUT_SECONDS = 10


class GateConfigError(RuntimeError):
    """Raised when the gate cannot trust its inputs."""


class ExternalToolError(RuntimeError):
    """Raised when a tool the gate runs does not finish in time."""


class GrowthCheckError(Exception):
    """The scan finished but the baseline growth check could not run."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


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
            env=git_environment(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(
            f"unused-argument gate: git {args[0]} timed out after {timeout:g}s"
        ) from exc
    except OSError as exc:
        raise GateConfigError(f"cannot run git: {exc}") from exc


def describe_ruff(repo_root: Path, ruff: Sequence[str], deadline: Deadline) -> str:
    """Return the ruff command and its version, for the gate's output.

    The finding set depends on the ruff version, so a failure names the ruff
    that produced it. A version call that fails reads ``version unknown``; it
    never changes the verdict.
    """
    timeout = deadline.timeout_for(RUFF_VERSION_TIMEOUT_SECONDS, "ruff --version")
    version = "version unknown"
    try:
        completed = subprocess.run(
            [*ruff, "--version"],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=git_environment(),
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return f"{' '.join(ruff)} ({version})"
    lines = completed.stdout.strip().splitlines()
    if completed.returncode == 0 and lines:
        version = lines[0][:80]
    return f"{' '.join(ruff)} ({version})"
