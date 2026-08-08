"""Capturing output written below Python, at the file-descriptor level.

Split out of ``hook_dispatch`` because none of it is about hooks, shims, or
policy. It answers one question, how to retain everything written to stdout and
stderr while a callback runs, including writes from a child process that never
passes through ``sys.stdout``. That is a POSIX descriptor concern with its own
reasons to change: buffering, encoding, restoration on failure.

Leaving it in the dispatcher meant seven functions and roughly a third of the
file changed for descriptor reasons while the rest changed for policy reasons,
which is two reasons to change in one module.

Refs #4672.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable
from typing import BinaryIO, TextIO


def open_capture_stream(fd: int) -> TextIO:
    """Return a UTF-8 text stream over a duplicate of ``fd``."""
    duplicate = os.dup(fd)
    try:
        return os.fdopen(
            duplicate,
            "w",
            buffering=1,
            encoding="utf-8",
            errors="replace",
            newline="",
        )
    except (OSError, ValueError):
        os.close(duplicate)
        raise


def save_output_fds(capture_stderr: bool) -> tuple[int, int | None]:
    """Flush host streams and duplicate output descriptors for restoration."""
    sys.stdout.flush()
    if capture_stderr:
        sys.stderr.flush()
    saved_stdout_fd = os.dup(1)
    try:
        saved_stderr_fd = os.dup(2) if capture_stderr else None
    except OSError:
        os.close(saved_stdout_fd)
        raise
    return saved_stdout_fd, saved_stderr_fd


def restore_output_fds(saved_stdout_fd: int, saved_stderr_fd: int | None) -> None:
    """Restore and close saved output descriptors."""
    stdout_error: OSError | None = None
    try:
        os.dup2(saved_stdout_fd, 1)
    except OSError as exc:
        stdout_error = exc
    finally:
        os.close(saved_stdout_fd)

    if saved_stderr_fd is not None:
        try:
            os.dup2(saved_stderr_fd, 2)
        finally:
            os.close(saved_stderr_fd)
    if stdout_error is not None:
        raise stdout_error


def read_capture(captured_file: BinaryIO) -> str:
    """Read one binary temporary capture file as replacement-safe UTF-8."""
    captured_file.flush()
    captured_file.seek(0)
    return captured_file.read().decode("utf-8", errors="replace")


def capture_process_output(
    name: str,
    runner: Callable[[], int],
    *,
    capture_stderr: bool,
    diagnostic_prefix: str = "hook-dispatch",
    failure_exit: int,
) -> tuple[int, str, str, str | None]:
    """Redirect selected process channels, run the callback, and read output."""
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with (
        tempfile.TemporaryFile() as captured_stdout_file,
        tempfile.TemporaryFile() as captured_stderr_file,
    ):
        captured_stdout_stream = None
        captured_stderr_stream = None
        capture_error: str | None = None
        try:
            os.dup2(captured_stdout_file.fileno(), 1)
            captured_stdout_stream = open_capture_stream(1)
            if capture_stderr:
                os.dup2(captured_stderr_file.fileno(), 2)
                captured_stderr_stream = open_capture_stream(2)
        except (OSError, ValueError) as exc:
            capture_error = (
                f"{diagnostic_prefix}: process output capture setup failed "
                f"for {name}: {exc}; observer not run"
            )
            code = failure_exit
        else:
            sys.stdout = captured_stdout_stream
            if captured_stderr_stream is not None:
                sys.stderr = captured_stderr_stream
            try:
                code = runner()
                captured_stdout_stream.flush()
                if captured_stderr_stream is not None:
                    captured_stderr_stream.flush()
            except (OSError, ValueError) as exc:
                capture_error = (
                    f"{diagnostic_prefix}: process output capture failed for {name}: {exc}"
                )
                code = failure_exit
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            if captured_stdout_stream is not None:
                captured_stdout_stream.close()
            if captured_stderr_stream is not None:
                captured_stderr_stream.close()

        raw_stdout = read_capture(captured_stdout_file)
        raw_stderr = read_capture(captured_stderr_file) if capture_stderr else ""
        return code, raw_stdout, raw_stderr, capture_error


def run_capturing_process_output(
    name: str,
    runner: Callable[[], int],
    *,
    capture_stderr: bool = False,
    diagnostic_prefix: str = "hook-dispatch",
    failure_exit: int,
) -> tuple[int, str, str]:
    """Run a callback while retaining selected process output channels."""
    original_stderr = sys.stderr
    try:
        saved_stdout_fd, saved_stderr_fd = save_output_fds(capture_stderr)
    except (OSError, ValueError) as exc:
        print(
            f"{diagnostic_prefix}: process output capture unavailable for "
            f"{name}: {exc}; observer not run",
            file=original_stderr,
        )
        return failure_exit, "", ""

    try:
        try:
            code, raw_stdout, raw_stderr, capture_error = capture_process_output(
                name,
                runner,
                capture_stderr=capture_stderr,
                diagnostic_prefix=diagnostic_prefix,
                failure_exit=failure_exit,
            )
        except (OSError, ValueError) as exc:
            code, raw_stdout, raw_stderr = failure_exit, "", ""
            capture_error = (
                f"{diagnostic_prefix}: process output capture setup failed "
                f"for {name}: {exc}; observer not run"
            )
    finally:
        restore_output_fds(saved_stdout_fd, saved_stderr_fd)

    if capture_error is not None:
        print(capture_error, file=original_stderr)
    return code, raw_stdout, raw_stderr


def run_capturing_process_stdout(
    name: str,
    runner: Callable[[], int],
    *,
    diagnostic_prefix: str = "hook-dispatch",
    failure_exit: int,
) -> tuple[int, str]:
    """Run a callback while retaining Python, file-descriptor, and child stdout."""
    code, raw_stdout, _ = run_capturing_process_output(
        name,
        runner,
        diagnostic_prefix=diagnostic_prefix,
        failure_exit=failure_exit,
    )
    return code, raw_stdout
