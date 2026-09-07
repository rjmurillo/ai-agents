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

# Reason codes for the typed evidence contract (issue #5635).
from scripts.validation.evidence import (
    REASON_PROCESS_SIGNALED,
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
)

# The exit code :func:`_run_subprocess` returns when the child never produced
# one of its own: a timeout or a missing executable. Any other non-zero value
# came from the child itself.
_SENTINEL_EXIT = -1


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


def classify_subprocess_failure(exit_code: int, stderr: str, *, default: str) -> str:
    """Return the evidence reason code for a failed :func:`_run_subprocess` call.

    A timed-out child and a child that ran and exited non-zero are different
    findings with different remedies, and ``_run_subprocess`` reports both as
    exit ``-1`` versus a real code. Collapsing them into one reason costs the
    reader the first diagnostic step, which is the defect
    ``.claude/rules/ci-scripts.md`` MUST 14 records for the count ratchets and
    the reason ``evidence.py`` keeps BLOCKED and UNKNOWN apart.

    The two markers are :func:`_run_subprocess`'s documented contract,
    quoted verbatim from the source above:

        marker = f"Command timed out after {timeout}s"
        return -1, "", f"Command not found: {args[0]}"

    A negative return code that matches neither marker is a child killed by a
    signal: :func:`subprocess.run` reports that as the negated signal number,
    so ``-9`` is SIGKILL and ``-15`` is SIGTERM. Those are not verdicts, and
    before issue #5653 they fell through to ``default`` and were read as the
    child's own findings exit: an actionlint killed by the OOM killer became
    workflow violations that do not exist, and a killed yamllint became a
    tolerated-findings PASS.

    A bare ``-1`` with no marker belongs in that class too. This wrapper always
    writes a marker when it returns ``-1`` itself, so a markerless ``-1`` is not
    the sentinel, it is SIGHUP.

    The rule is therefore the sign, not the sentinel: a negative code means the
    child did not choose its own exit, so it cannot carry a finding.

    ``default`` is the caller's own reason for an ordinary non-zero exit, since
    only the caller knows what its child was doing (issue #5635).
    """
    if exit_code == _SENTINEL_EXIT:
        if "Command timed out after" in stderr:
            return REASON_TIMEOUT
        if "Command not found:" in stderr:
            return REASON_TOOL_ABSENT
    if exit_code < 0:
        return REASON_PROCESS_SIGNALED
    return default
