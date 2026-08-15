"""Timed shim execution for the Copilot hook dispatcher.

Timeout and launch-failure policy (issue #5013)
------------------------------------------------
A child-process timeout is an infrastructure event, not a policy signal. The
shim did not run its relevance gate or its policy logic; it never determined
whether the tool call is dangerous. Converting that uncertainty into a deny
(exit 2) makes every registered shim a latent denial-of-service: any
contention, antivirus scan, or cold-start spike that exceeds the bound blocks
the tool for the entire session.

This module therefore treats timeout and launch failure as ALLOW (exit 0) with
a visible warning on stderr. The host still owns the cumulative event timeout
(PreToolUse timeoutSec in hooks.json); a shim that neither allowed nor denied
within its bound has no policy standing to block the call.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ALLOW_EXIT = 0
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
    """Run one timed shim in a child process so timeout can kill it.

    Returns ALLOW_EXIT (0) on timeout or launch failure. A timed-out shim has
    not evaluated its policy; denying would convert infrastructure latency into
    a tool block for unrelated commands (issue #5013, 127 false denials in one
    session). The host's cumulative event timeout remains the backstop.
    """
    try:
        completed = subprocess.run(
            # -E -s, not -I. All three drop PYTHONPATH and user site-packages,
            # which is the injection protection this launcher needs. -I also
            # implies -P, which drops the script's own directory from sys.path,
            # and every timed shim imports its sibling _bootstrap. Under -I the
            # child died with ModuleNotFoundError before its policy ran, so the
            # markdownlint push guard was disabled at runtime (issue #4825).
            [sys.executable, "-E", "-s", str(shim_path)],
            input=raw_stdin,
            stdout=subprocess.PIPE if capture_stdout else None,
            stderr=subprocess.PIPE if capture_stderr else None,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        print(
            f"hook-dispatch: shim {name} timed out after {timeout_sec:g}s; "
            f"allowing (infrastructure timeout is not a policy denial). "
            f"Reinstall if persistent: /install-plugin rjmurillo/ai-agents",
            file=sys.stderr,
        )
        return ALLOW_EXIT, "", ""
    except OSError as exc:
        print(
            f"hook-dispatch: shim {name} failed to launch: {exc}; "
            f"allowing (launch failure is not a policy denial). "
            f"Reinstall if persistent: /install-plugin rjmurillo/ai-agents",
            file=sys.stderr,
        )
        return ALLOW_EXIT, "", ""
    return (
        completed.returncode,
        _decode_completed_stream(completed.stdout),
        _decode_completed_stream(completed.stderr),
    )
