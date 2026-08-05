"""Run one text-only Copilot completion over Agent Client Protocol stdin."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Literal, TextIO, cast

from _copilot_process_tree import ProcessTree, windows_creation_flags

_PROTOCOL_VERSION = 1
_MAX_CAPTURE_CHARS = 4 * 1024 * 1024
_MAX_PROTOCOL_LINE_CHARS = 1024 * 1024
_MAX_PROTOCOL_CHARS = 4 * 1024 * 1024
_STDOUT_QUEUE_LINES = 64
_STDERR_CLASSIFICATION_CHARS = 4096
_PROCESS_WAIT_SECONDS = 5.0
_READER_JOIN_SECONDS = 5.0
_QUEUE_WAIT_SECONDS = 0.1
_TOOL_UPDATE_NAMES = frozenset({"tool_call", "tool_call_update"})
_AUTH_HINTS = (
    "auth",
    "forbidden",
    "login",
    "not logged in",
    "permission denied",
    "sign in",
    "unauthorized",
)


class ACPProcessError(RuntimeError):
    """A Copilot ACP child failed, with output retained only for classification."""

    def __init__(self, returncode: int, stderr: str) -> None:
        super().__init__("Copilot ACP process failed")
        self.returncode = returncode
        self.stderr = stderr


ACPErrorCategory = Literal[
    "authentication failed",
    "provider failure",
    "rate limit",
    "request timed out",
]


class ACPProviderError(RuntimeError):
    """A fixed, redacted provider failure returned over ACP JSON-RPC."""

    def __init__(self, category: ACPErrorCategory) -> None:
        super().__init__(
            f"Copilot ACP provider error: error={category}; "
            "provider details redacted"
        )
        self.category = category


@dataclass
class _ProcessStreams:
    process: subprocess.Popen[str]
    process_tree: ProcessTree
    stdout_lines: queue.Queue[str | BaseException | None]
    stderr_chunks: list[str]
    stop_readers: threading.Event
    stdout_thread: threading.Thread
    stderr_thread: threading.Thread
    protocol_chars: int = 0
    answer_chars: int = 0


def _put_stdout(
    lines: queue.Queue[str | BaseException | None],
    item: str | BaseException | None,
    stop_readers: threading.Event,
) -> None:
    while not stop_readers.is_set():
        try:
            lines.put(item, timeout=_QUEUE_WAIT_SECONDS)
            return
        except queue.Full:
            continue


def _read_stdout(
    stream: TextIO,
    lines: queue.Queue[str | BaseException | None],
    stop_readers: threading.Event,
) -> None:
    try:
        while not stop_readers.is_set():
            line = stream.readline(_MAX_PROTOCOL_LINE_CHARS + 1)
            if not line:
                return
            if len(line) > _MAX_PROTOCOL_LINE_CHARS:
                _put_stdout(
                    lines,
                    RuntimeError("Copilot ACP protocol line exceeded the size limit"),
                    stop_readers,
                )
                return
            _put_stdout(lines, line, stop_readers)
    except (OSError, ValueError):
        pass
    finally:
        _put_stdout(lines, None, stop_readers)


def _read_stderr(stream: TextIO, chunks: list[str]) -> None:
    remaining = _STDERR_CLASSIFICATION_CHARS
    try:
        while data := stream.read(1024):
            if remaining <= 0:
                continue
            kept = data[:remaining]
            chunks.append(kept)
            remaining -= len(kept)
    except (OSError, ValueError):
        pass


def _start_process(
    argv: list[str],
    *,
    cwd: str,
    env: dict[str, str],
) -> _ProcessStreams:
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        shell=False,
        start_new_session=os.name != "nt",
        creationflags=windows_creation_flags(),
    )
    try:
        process_tree = ProcessTree(process)
    except BaseException:
        process.kill()
        process.wait()
        raise
    if process.stdout is None or process.stderr is None:
        process_tree.terminate(force=True)
        process_tree.close()
        raise RuntimeError("Copilot ACP process pipes were unavailable")
    stdout_lines: queue.Queue[str | BaseException | None] = queue.Queue(
        maxsize=_STDOUT_QUEUE_LINES
    )
    stderr_chunks: list[str] = []
    stop_readers = threading.Event()
    stdout_thread = threading.Thread(
        target=_read_stdout,
        args=(process.stdout, stdout_lines, stop_readers),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_stderr,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    return _ProcessStreams(
        process,
        process_tree,
        stdout_lines,
        stderr_chunks,
        stop_readers,
        stdout_thread,
        stderr_thread,
    )


def _send_request(
    process: subprocess.Popen[str],
    request_id: int,
    method: str,
    params: dict[str, object],
) -> None:
    if process.stdin is None:
        raise RuntimeError("Copilot ACP stdin was unavailable")
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }
    process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    process.stdin.flush()


def _consume_update(
    message: dict[str, object],
    answer_chunks: list[str],
    streams: _ProcessStreams,
) -> None:
    params = message.get("params")
    if not isinstance(params, dict):
        return
    update = params.get("update")
    if not isinstance(update, dict):
        return
    update_name = update.get("sessionUpdate")
    if update_name in _TOOL_UPDATE_NAMES:
        raise RuntimeError("Copilot ACP attempted a disabled tool")
    if update_name != "agent_message_chunk":
        return
    content = update.get("content")
    if not isinstance(content, dict) or content.get("type") != "text":
        raise RuntimeError("Copilot ACP returned a malformed text chunk")
    text = content.get("text")
    if not isinstance(text, str):
        raise RuntimeError("Copilot ACP returned a malformed text chunk")
    streams.answer_chars += len(text)
    if streams.answer_chars > _MAX_CAPTURE_CHARS:
        raise RuntimeError("Copilot ACP response exceeded the size limit")
    answer_chunks.append(text)


def _parse_message(raw_line: str) -> dict[str, object]:
    if len(raw_line) > _MAX_CAPTURE_CHARS:
        raise RuntimeError("Copilot ACP protocol message exceeded the size limit")
    try:
        parsed = json.loads(raw_line)
    except json.JSONDecodeError:
        raise RuntimeError("Copilot ACP returned malformed protocol JSON") from None
    if not isinstance(parsed, dict):
        raise RuntimeError("Copilot ACP returned a malformed protocol message")
    return cast(dict[str, object], parsed)


def _provider_error(payload: object) -> ACPProviderError:
    message = payload.get("message") if isinstance(payload, dict) else None
    lowered = message[:_STDERR_CLASSIFICATION_CHARS].lower() if isinstance(message, str) else ""
    if any(hint in lowered for hint in _AUTH_HINTS):
        category: ACPErrorCategory = "authentication failed"
    elif "rate limit" in lowered or "too many requests" in lowered:
        category = "rate limit"
    elif "timed out" in lowered or "timeout" in lowered:
        category = "request timed out"
    else:
        category = "provider failure"
    return ACPProviderError(category)


def _wait_for_response(
    streams: _ProcessStreams,
    request_id: int,
    *,
    deadline: float,
    timeout: float,
    answer_chunks: list[str],
) -> dict[str, object]:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(streams.process.args, timeout) from None
        try:
            raw_line = streams.stdout_lines.get(timeout=remaining)
        except queue.Empty:
            raise subprocess.TimeoutExpired(streams.process.args, timeout) from None
        if raw_line is None:
            returncode = _close_process(streams)
            raise ACPProcessError(
                returncode,
                "".join(streams.stderr_chunks),
            )
        if isinstance(raw_line, BaseException):
            raise raw_line
        streams.protocol_chars += len(raw_line)
        if streams.protocol_chars > _MAX_PROTOCOL_CHARS:
            raise RuntimeError("Copilot ACP protocol exceeded the size limit")
        message = _parse_message(raw_line)
        if message.get("id") == request_id:
            if "error" in message:
                raise _provider_error(message.get("error")) from None
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Copilot ACP returned a malformed result")
            return cast(dict[str, object], result)
        if "id" in message and isinstance(message.get("method"), str):
            raise RuntimeError("Copilot ACP requested a disabled client capability")
        if message.get("method") == "session/update":
            _consume_update(message, answer_chunks, streams)


def _join_readers(streams: _ProcessStreams) -> bool:
    deadline = time.monotonic() + _READER_JOIN_SECONDS
    for reader in (streams.stdout_thread, streams.stderr_thread):
        reader.join(max(0.0, deadline - time.monotonic()))
    if not streams.stdout_thread.is_alive() and not streams.stderr_thread.is_alive():
        return True

    streams.stop_readers.set()
    streams.process_tree.terminate(force=True)
    deadline = time.monotonic() + _READER_JOIN_SECONDS
    for reader in (streams.stdout_thread, streams.stderr_thread):
        reader.join(max(0.0, deadline - time.monotonic()))
    return not streams.stdout_thread.is_alive() and not streams.stderr_thread.is_alive()


def _wait_for_process(streams: _ProcessStreams) -> int:
    process = streams.process
    try:
        return process.wait(timeout=_PROCESS_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        streams.process_tree.terminate(force=False)
    try:
        return process.wait(timeout=_PROCESS_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        streams.process_tree.terminate(force=True)
        return process.wait(timeout=_PROCESS_WAIT_SECONDS)


def _close_process(streams: _ProcessStreams) -> int:
    process = streams.process
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    returncode = _wait_for_process(streams)
    if not _join_readers(streams):
        raise RuntimeError("Copilot ACP reader cleanup timed out")
    streams.process_tree.close()
    return returncode


def _stop_process(streams: _ProcessStreams) -> None:
    process = streams.process
    streams.stop_readers.set()
    streams.process_tree.terminate(force=False)
    if process.poll() is None:
        try:
            process.wait(timeout=_PROCESS_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            streams.process_tree.terminate(force=True)
            process.wait(timeout=_PROCESS_WAIT_SECONDS)
    _join_readers(streams)
    streams.process_tree.close()


def _request(
    streams: _ProcessStreams,
    request_id: int,
    method: str,
    params: dict[str, object],
    *,
    deadline: float,
    timeout: float,
    answer_chunks: list[str],
) -> dict[str, object]:
    _send_request(streams.process, request_id, method, params)
    return _wait_for_response(
        streams,
        request_id,
        deadline=deadline,
        timeout=timeout,
        answer_chunks=answer_chunks,
    )


def _run_session(
    streams: _ProcessStreams,
    prompt: str,
    cwd: str,
    *,
    deadline: float,
    timeout: float,
) -> list[str]:
    answer_chunks: list[str] = []
    initialized = _request(
        streams,
        1,
        "initialize",
        {
            "protocolVersion": _PROTOCOL_VERSION,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
            "clientInfo": {"name": "ai-agents-eval", "version": "1"},
        },
        deadline=deadline,
        timeout=timeout,
        answer_chunks=answer_chunks,
    )
    if initialized.get("protocolVersion") != _PROTOCOL_VERSION:
        raise RuntimeError("Copilot ACP negotiated an unsupported protocol")
    created = _request(
        streams,
        2,
        "session/new",
        {"cwd": cwd, "mcpServers": []},
        deadline=deadline,
        timeout=timeout,
        answer_chunks=answer_chunks,
    )
    session_id = created.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("Copilot ACP returned no session identifier")
    _request(
        streams,
        3,
        "session/prompt",
        {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt}]},
        deadline=deadline,
        timeout=timeout,
        answer_chunks=answer_chunks,
    )
    _request(
        streams,
        4,
        "session/close",
        {"sessionId": session_id},
        deadline=deadline,
        timeout=timeout,
        answer_chunks=answer_chunks,
    )
    return answer_chunks


def run_acp_completion(
    argv: list[str],
    prompt: str,
    *,
    cwd: str,
    env: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Send ``prompt`` over ACP stdin and return the text response."""
    streams = _start_process(argv, cwd=cwd, env=env)
    deadline = time.monotonic() + timeout
    try:
        answer_chunks = _run_session(
            streams,
            prompt,
            cwd,
            deadline=deadline,
            timeout=timeout,
        )
        returncode = _close_process(streams)
    except BaseException:
        _stop_process(streams)
        raise
    stderr = "".join(streams.stderr_chunks)
    if returncode != 0:
        raise ACPProcessError(returncode, stderr)
    return subprocess.CompletedProcess(
        args=argv,
        returncode=returncode,
        stdout="".join(answer_chunks),
        stderr=stderr,
    )
