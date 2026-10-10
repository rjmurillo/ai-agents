"""Read-only `gh api` GET calls sharing one deadline (issue #6239).

Fixed argument lists, no shell. `scripts/validation/testmon_seed.py` documents
the trust model and the fallbacks.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

GhRunner = Callable[[list[str], float], "subprocess.CompletedProcess[bytes]"]


def run_gh(args: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


class Budget:
    """One shared deadline for every request in a fetch."""

    def __init__(self, seconds: float, runner: GhRunner) -> None:
        self._deadline = time.monotonic() + seconds
        self._runner = runner

    def get(self, endpoint: str) -> bytes:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("seed fetch deadline passed")
        try:
            result = self._runner([endpoint], remaining)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("gh api timed out") from error
        if result.returncode != 0:
            tail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
            raise RuntimeError(f"gh api failed: {tail[0] if tail else 'no output'}")
        return result.stdout
