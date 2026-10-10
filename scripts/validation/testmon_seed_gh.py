"""Read-only `gh api` GET calls sharing one deadline (issue #6239).

Fixed argument lists, no shell. `scripts/validation/testmon_seed.py` documents
the trust model and the fallbacks.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO

GhRunner = Callable[[list[str], float], "subprocess.CompletedProcess[bytes]"]
Downloader = Callable[[str, Path, float, int], None]
CHUNK_BYTES = 1024 * 1024


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

    def remaining(self) -> float:
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("seed fetch deadline passed")
        return left


def download_to_file(
    endpoint: str,
    destination: Path,
    timeout_seconds: float,
    max_bytes: int,
    command: Sequence[str] = ("gh", "api"),
) -> None:
    """Stream ``gh api <endpoint>`` into a new file, stopping at ``max_bytes``.

    The file is created with O_CREAT|O_EXCL|O_NOFOLLOW, so an existing file or a
    symlink at ``destination`` fails the open. The size cap is enforced while
    reading, not after, and a timer kills a child that outlives the deadline.

    Raises:
        ValueError: the download exceeded ``max_bytes``.
        TimeoutError: the child outlived ``timeout_seconds``.
        RuntimeError: the child exited nonzero.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    expired = threading.Event()
    with os.fdopen(os.open(destination, flags, 0o600), "wb") as handle:
        process = subprocess.Popen(
            [*command, endpoint], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )

        def expire() -> None:
            expired.set()
            process.kill()

        timer = threading.Timer(timeout_seconds, expire)
        timer.start()
        try:
            _copy_capped(process.stdout, handle, max_bytes)
            returncode = process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
    if expired.is_set():
        raise TimeoutError("gh api download timed out")
    if returncode != 0:
        raise RuntimeError(f"gh api download failed (exit {returncode})")


def _copy_capped(stream: IO[bytes] | None, handle: IO[bytes], max_bytes: int) -> None:
    if stream is None:
        raise RuntimeError("gh api produced no output stream")
    written = 0
    while chunk := stream.read(CHUNK_BYTES):
        written += len(chunk)
        if written > max_bytes:
            raise ValueError("download larger than the size cap")
        handle.write(chunk)
