#!/usr/bin/env python3
"""Subprocess wrapper shared by the pre-PR validation check modules.

Split out of ``checks_common`` (issue #4955) so the timeout path can preserve
the partial stdout and stderr Python leaves on ``TimeoutExpired``. Discarding
that output hid the ratchet or validator result that ran just before a
merge-tree timeout (issue #4876): the maintainer saw the timeout but not the
diagnostic that explained where the child stopped.

``checks_common`` re-exports :func:`_run_subprocess`, so every existing
``from checks_common import _run_subprocess`` keeps resolving.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from scripts.cli_exec import resolve_executable


def _decode_stream(data: bytes | str | None) -> str:
    """Decode a captured subprocess stream with UTF-8 replacement semantics.

    ``subprocess.run(encoding="utf-8", errors="replace")`` returns ``str`` on
    the happy path, but a timeout raises inside ``Popen`` before the decode
    step, so ``TimeoutExpired.stdout`` and ``.stderr`` arrive as raw ``bytes``
    on POSIX and as already-decoded ``str`` on the Windows
    kill-then-communicate path. Match the happy-path ``errors="replace"``
    decode and treat a missing stream as empty.
    """
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _run_subprocess(
    args: list[str],
    timeout: int = 300,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess after resolving its executable for the target platform.

    When ``env`` is provided it replaces the child environment entirely, so
    callers that only want to add a variable should merge it with
    ``os.environ`` themselves before passing it in.

    On ``subprocess.TimeoutExpired`` the partial stdout and stderr the child
    flushed before the timeout are preserved (issue #4955) instead of being
    discarded. The timeout stays a failure: the exit code is ``-1`` and the
    ``Command timed out after Ns`` marker stays in the returned stderr, after
    any partial stderr the child produced.
    """
    try:
        executable = args[0] if os.path.dirname(args[0]) else resolve_executable(args[0], env=env)
        command = [executable, *args[1:]]
        result = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired as exc:
        partial_stdout = _decode_stream(exc.stdout)
        partial_stderr = _decode_stream(exc.stderr)
        marker = f"Command timed out after {timeout}s"
        combined_stderr = f"{partial_stderr}\n{marker}" if partial_stderr else marker
        return -1, partial_stdout, combined_stderr
