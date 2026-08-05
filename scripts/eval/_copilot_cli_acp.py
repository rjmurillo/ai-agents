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
class _CharacterCounter:
    value: int = 0


@dataclass
class _ProcessStreams:
    process: subprocess.Popen[str]
    process_tree: ProcessTree
    stdout_lines: queue.Queue[str | BaseException | None]
    stderr_chunks: list[str]
    stop_readers: threading.Event
    stdout_thread: threading.Thread
    stderr_thread: threading.Thread
    protocol_chars: _CharacterCounter
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
    protocol_chars: _CharacterCounter,
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
            protocol_chars.value += len(line)
            if protocol_chars.value > _MAX_PROTOCOL_CHARS:
                _put_stdout(
                    lines,
                    RuntimeError("Copilot ACP protocol exceeded the size limit"),
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
    protocol_chars = _CharacterCounter()
    stdout_thread = threading.Thread(
        target=_read_stdout,
        args=(process.stdout, stdout_lines, stop_readers, protocol_chars),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_stderr,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    started_readers: list[threading.Thread] = []
    try:
        stdout_thread.start()
        started_readers.append(stdout_thread)
        stderr_thread.start()
        started_readers.append(stderr_thread)
    except BaseException:
        stop_readers.set()
        process_tree.terminate(force=True)
        if process.poll() is None:
            process.wait(timeout=_PROCESS_WAIT_SECONDS)
        for reader in started_readers:
            reader.join(timeout=_READER_JOIN_SECONDS)
        process_tree.close()
        raise
    return _ProcessStreams(
        process,
        process_tree,
        stdout_lines,
        stderr_chunks,
        stop_readers,
        stdout_thread,
        stderr_thread,
        protocol_chars,
    )


def _send_request(
    streams: _ProcessStreams,
    request_id: int,
    method: str,
    params: dict[str, object],
    *,
    deadline: float,
    timeout: float,
) -> None:
    process = streams.process
    if process.stdin is None:
        raise RuntimeError("Copilot ACP stdin was unavailable")
    stdin = process.stdin
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }
    completed = threading.Event()
    write_errors: queue.Queue[BaseException] = queue.Queue(maxsize=1)

    def write_payload() -> None:
        try:
            stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            stdin.flush()
        except (OSError, ValueError) as exc:
            write_errors.put(exc)
        finally:
            completed.set()

    writer = threading.Thread(target=write_payload, daemon=True)
    writer.start()
    while not completed.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            streams.process_tree.terminate(force=True)
            raise subprocess.TimeoutExpired(process.args, timeout) from None
        if completed.wait(min(remaining, _QUEUE_WAIT_SECONDS)):
            break
        returncode = process.poll()
        if returncode is not None:
            streams.process_tree.terminate(force=True)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout) from None
            streams.stderr_thread.join(min(remaining, _READER_JOIN_SECONDS))
            if streams.stderr_thread.is_alive():
                raise RuntimeError("Copilot ACP stderr reader cleanup timed out")
            raise ACPProcessError(
                returncode,
                "".join(streams.stderr_chunks),
            )
    if not write_errors.empty():
        raise RuntimeError("Copilot ACP stdin write failed") from None


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
    terminated_descendants = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(streams.process.args, timeout) from None
        try:
            raw_line = streams.stdout_lines.get(
                timeout=min(remaining, _QUEUE_WAIT_SECONDS)
            )
        except queue.Empty:
            if streams.process.poll() is not None and not terminated_descendants:
                streams.process_tree.terminate(force=True)
                terminated_descendants = True
            continue
        if raw_line is None:
            returncode = _close_process(
                streams,
                deadline=deadline,
                timeout=timeout,
            )
            raise ACPProcessError(
                returncode,
                "".join(streams.stderr_chunks),
            )
        if isinstance(raw_line, BaseException):
            raise raw_line
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


def _join_readers(
    streams: _ProcessStreams,
    *,
    deadline: float,
    timeout: float,
) -> bool:
    phase_deadline = min(
        deadline,
        time.monotonic() + _READER_JOIN_SECONDS,
    )
    for reader in (streams.stdout_thread, streams.stderr_thread):
        reader.join(max(0.0, phase_deadline - time.monotonic()))
    if not streams.stdout_thread.is_alive() and not streams.stderr_thread.is_alive():
        return True

    streams.stop_readers.set()
    streams.process_tree.terminate(force=True)
    if deadline <= time.monotonic():
        raise subprocess.TimeoutExpired(streams.process.args, timeout) from None
    phase_deadline = min(
        deadline,
        time.monotonic() + _READER_JOIN_SECONDS,
    )
    for reader in (streams.stdout_thread, streams.stderr_thread):
        reader.join(max(0.0, phase_deadline - time.monotonic()))
    return not streams.stdout_thread.is_alive() and not streams.stderr_thread.is_alive()


def _remaining_process_wait(
    streams: _ProcessStreams,
    deadline: float,
    timeout: float,
) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        streams.process_tree.terminate(force=True)
        raise subprocess.TimeoutExpired(streams.process.args, timeout) from None
    return min(_PROCESS_WAIT_SECONDS, remaining)


def _wait_for_process(
    streams: _ProcessStreams,
    *,
    deadline: float,
    timeout: float,
) -> int:
    process = streams.process
    try:
        return process.wait(
            timeout=_remaining_process_wait(streams, deadline, timeout)
        )
    except subprocess.TimeoutExpired:
        streams.process_tree.terminate(force=False)
    try:
        return process.wait(
            timeout=_remaining_process_wait(streams, deadline, timeout)
        )
    except subprocess.TimeoutExpired:
        streams.process_tree.terminate(force=True)
        return process.wait(
            timeout=_remaining_process_wait(streams, deadline, timeout)
        )


def _close_process(
    streams: _ProcessStreams,
    *,
    deadline: float,
    timeout: float,
) -> int:
    process = streams.process
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    returncode = _wait_for_process(
        streams,
        deadline=deadline,
        timeout=timeout,
    )
    if not _join_readers(streams, deadline=deadline, timeout=timeout):
        raise RuntimeError("Copilot ACP reader cleanup timed out")
    streams.process_tree.close()
    return returncode


def _stop_process(
    streams: _ProcessStreams,
    *,
    deadline: float,
    timeout: float,
) -> None:
    process = streams.process
    streams.stop_readers.set()
    streams.process_tree.terminate(force=False)
    if process.poll() is None:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=min(_PROCESS_WAIT_SECONDS, remaining))
        except subprocess.TimeoutExpired:
            streams.process_tree.terminate(force=True)
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=min(_PROCESS_WAIT_SECONDS, remaining))
            except subprocess.TimeoutExpired:
                pass
    try:
        _join_readers(streams, deadline=deadline, timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
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
    _send_request(
        streams,
        request_id,
        method,
        params,
        deadline=deadline,
        timeout=timeout,
    )
    return _wait_for_response(
        streams,
        request_id,
        deadline=deadline,
        timeout=timeout,
        answer_chunks=answer_chunks,
    )


def _drain_stdout_after_close(
    streams: _ProcessStreams,
    answer_chunks: list[str],
    *,
    deadline: float,
    timeout: float,
) -> None:
    process = streams.process
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    terminated_descendants = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(streams.process.args, timeout) from None
        try:
            raw_line = streams.stdout_lines.get(
                timeout=min(remaining, _QUEUE_WAIT_SECONDS)
            )
        except queue.Empty:
            if streams.process.poll() is not None and not terminated_descendants:
                streams.process_tree.terminate(force=True)
                terminated_descendants = True
            continue
        if raw_line is None:
            return
        if isinstance(raw_line, BaseException):
            raise raw_line
        message = _parse_message(raw_line)
        if "id" in message and isinstance(message.get("method"), str):
            raise RuntimeError("Copilot ACP requested a disabled client capability")
        if message.get("method") == "session/update":
            _consume_update(message, answer_chunks, streams)


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
        _drain_stdout_after_close(
            streams,
            answer_chunks,
            deadline=deadline,
            timeout=timeout,
        )
        returncode = _close_process(
            streams,
            deadline=deadline,
            timeout=timeout,
        )
    except BaseException:
        _stop_process(streams, deadline=deadline, timeout=timeout)
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
