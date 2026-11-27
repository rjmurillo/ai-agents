#!/usr/bin/env python3
"""Incremental pipe communication for Windows validation children.

CPython's Windows ``Popen.communicate`` uses reader threads whose unbounded
``read()`` calls finish only at pipe EOF. A descendant that survives its
parent can therefore hide output the parent already flushed and can keep the
runner's post-kill drain alive past its deadline. These helpers keep the
reader-thread shape Windows requires, but read bounded chunks and let the
runner abandon a pipe only after the drain deadline has already expired.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import threading
import time
from dataclasses import dataclass

_PIPE_CHUNK_SIZE = 65536
_PIPE_STATE_ATTR = "_ai_agents_pipe_readers"
_POPEN_CLASS = subprocess.Popen


def _decode_pipe_bytes(data: bytes | None) -> str:
    if data is None:
        return ""
    return data.decode("utf-8", errors="replace")


@dataclass
class _PipeReader:
    """One background pipe reader and every byte it has observed so far."""

    chunks: list[bytes]
    thread: threading.Thread


def _read_pipe_chunks(stream: object, chunks: list[bytes]) -> None:
    """Append pipe bytes as they arrive instead of waiting for EOF once.

    CPython's Windows reader thread calls ``fh.read()`` with no size, so a
    descendant holding the pipe hides even the bytes the direct child already
    flushed. Sized ``read1`` calls return each available chunk and preserve
    the partial-output contract up to the drain deadline.
    """
    read = getattr(stream, "read1", None) or getattr(stream, "read", None)
    if read is None:
        return
    with contextlib.suppress(OSError, ValueError):
        while chunk := read(_PIPE_CHUNK_SIZE):
            chunks.append(chunk)


def _windows_pipe_readers(proc: subprocess.Popen[str]) -> dict[str, _PipeReader]:
    """Start or return the pipe readers owned by ``proc``."""
    existing = getattr(proc, _PIPE_STATE_ATTR, None)
    if isinstance(existing, dict):
        return existing

    readers: dict[str, _PipeReader] = {}
    for stream_name in ("stdout", "stderr"):
        stream = getattr(proc, stream_name, None)
        if stream is None:
            continue
        byte_stream = getattr(stream, "buffer", stream)
        chunks: list[bytes] = []
        thread = threading.Thread(
            target=_read_pipe_chunks,
            args=(byte_stream, chunks),
            daemon=True,
        )
        readers[stream_name] = _PipeReader(chunks, thread)
        thread.start()
    setattr(proc, _PIPE_STATE_ATTR, readers)
    return readers


def _reader_bytes(reader: _PipeReader | None) -> bytes | None:
    if reader is None:
        return None
    return b"".join(reader.chunks)


def _windows_pipe_output(
    proc: subprocess.Popen[str], readers: dict[str, _PipeReader], timeout: float | None
) -> subprocess.TimeoutExpired:
    """Build a timeout that carries the bytes observed before the deadline."""
    return subprocess.TimeoutExpired(
        proc.args,
        timeout or 0,
        output=_reader_bytes(readers.get("stdout")),
        stderr=_reader_bytes(readers.get("stderr")),
    )


def _communicate_windows(proc: subprocess.Popen[str], timeout: float | None) -> tuple[str, str]:
    """Read a Windows child's pipes incrementally within a total deadline."""
    readers = _windows_pipe_readers(proc)
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise _windows_pipe_output(proc, readers, timeout) from exc

    for reader in readers.values():
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        reader.thread.join(remaining)
    if any(reader.thread.is_alive() for reader in readers.values()):
        raise _windows_pipe_output(proc, readers, timeout)

    stdout = _decode_pipe_bytes(_reader_bytes(readers.get("stdout")))
    stderr = _decode_pipe_bytes(_reader_bytes(readers.get("stderr")))
    for stream_name in ("stdout", "stderr"):
        stream = getattr(proc, stream_name, None)
        if stream is not None:
            with contextlib.suppress(OSError, ValueError):
                stream.close()
    return stdout, stderr


def _communicate_with_partial(
    proc: subprocess.Popen[str], timeout: float | None
) -> tuple[str, str]:
    """Use incremental pipe reads on real Windows children, CPython elsewhere.

    The ``type`` check honors the ``Popen`` stand-ins these tests use to drive
    Windows control-flow seams on POSIX; a real Windows ``Popen`` gets the
    implementation above rather than CPython's EOF-only reader threads.
    """
    if os.name == "nt" and type(proc).communicate is _POPEN_CLASS.communicate:
        return _communicate_windows(proc, timeout)
    return proc.communicate(timeout=timeout)


def _abandon_live_pipe_streams(proc: subprocess.Popen[str]) -> None:
    """Keep ``Popen.__exit__`` from closing a pipe a reader thread owns.

    Closing a Windows pipe object in one thread can block behind a synchronous
    read in another. When the drain deadline has already expired, leaking that
    rare pipe until process exit is bounded; closing it here is not.
    """
    readers = getattr(proc, _PIPE_STATE_ATTR, None)
    if not isinstance(readers, dict):
        return
    for stream_name, reader in readers.items():
        if reader.thread.is_alive():
            setattr(proc, stream_name, None)
