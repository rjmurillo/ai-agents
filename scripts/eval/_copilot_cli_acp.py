"""Run one text-only Copilot completion over Agent Client Protocol stdin."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import TextIO, cast

_PROTOCOL_VERSION = 1
_MAX_CAPTURE_CHARS = 4 * 1024 * 1024
_STDERR_CLASSIFICATION_CHARS = 4096
_TOOL_UPDATE_NAMES = frozenset({"tool_call", "tool_call_update"})


class ACPProcessError(RuntimeError):
    """A Copilot ACP child failed, with output retained only for classification."""

    def __init__(self, returncode: int, stderr: str) -> None:
        super().__init__("Copilot ACP process failed")
        self.returncode = returncode
        self.stderr = stderr


@dataclass
class _ProcessStreams:
    process: subprocess.Popen[str]
    stdout_lines: queue.Queue[str | None]
    stderr_chunks: list[str]


def _read_stdout(stream: TextIO, lines: queue.Queue[str | None]) -> None:
    for line in stream:
        lines.put(line)
    lines.put(None)


def _read_stderr(stream: TextIO, chunks: list[str]) -> None:
    remaining = _STDERR_CLASSIFICATION_CHARS
    while data := stream.read(1024):
        if remaining <= 0:
            continue
        kept = data[:remaining]
        chunks.append(kept)
        remaining -= len(kept)


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
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("Copilot ACP process pipes were unavailable")
    stdout_lines: queue.Queue[str | None] = queue.Queue()
    stderr_chunks: list[str] = []
    threading.Thread(
        target=_read_stdout,
        args=(process.stdout, stdout_lines),
        daemon=True,
    ).start()
    threading.Thread(
        target=_read_stderr,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    ).start()
    return _ProcessStreams(process, stdout_lines, stderr_chunks)


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


def _consume_update(message: dict[str, object], answer_chunks: list[str]) -> None:
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
    answer_chunks.append(text)
    if sum(map(len, answer_chunks)) > _MAX_CAPTURE_CHARS:
        raise RuntimeError("Copilot ACP response exceeded the size limit")


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
            returncode = streams.process.poll()
            raise ACPProcessError(
                returncode if returncode is not None else 1,
                "".join(streams.stderr_chunks),
            )
        message = _parse_message(raw_line)
        if message.get("id") == request_id:
            if "error" in message:
                raise RuntimeError("Copilot ACP provider error") from None
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Copilot ACP returned a malformed result")
            return cast(dict[str, object], result)
        if "id" in message and isinstance(message.get("method"), str):
            raise RuntimeError("Copilot ACP requested a disabled client capability")
        if message.get("method") == "session/update":
            _consume_update(message, answer_chunks)


def _close_process(streams: _ProcessStreams) -> int:
    process = streams.process
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    try:
        return process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=5)


def _stop_process(streams: _ProcessStreams) -> None:
    process = streams.process
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


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
