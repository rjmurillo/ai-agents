"""Timed shim execution for the Copilot hook dispatcher."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BLOCK_EXIT = 2


def _decode_completed_stream(value: bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace")


def run_timed_shim(
    shim_path: Path,
    name: str,
    raw_stdin: bytes,
    timeout_sec: float,
    *,
    capture_stdout: bool = False,
    capture_stderr: bool = False,
) -> tuple[int, str, str]:
    """Run one timed shim in a child process so timeout can kill it."""
    try:
        completed = subprocess.run(
            [sys.executable, str(shim_path)],
            input=raw_stdin,
            stdout=subprocess.PIPE if capture_stdout else None,
            stderr=subprocess.PIPE if capture_stderr else None,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        print(
            f"hook-dispatch: shim {name} timed out after {timeout_sec:g}s; denying (fail-closed)",
            file=sys.stderr,
        )
        return BLOCK_EXIT, "", ""
    except OSError as exc:
        print(
            f"hook-dispatch: shim {name} failed to launch: {exc}; denying (fail-closed)",
            file=sys.stderr,
        )
        return BLOCK_EXIT, "", ""
    return (
        completed.returncode,
        _decode_completed_stream(completed.stdout),
        _decode_completed_stream(completed.stderr),
    )
