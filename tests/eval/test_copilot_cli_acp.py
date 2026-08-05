"""Runtime-contract tests for the text-only Copilot ACP transport."""

from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TextIO, cast

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(EVAL_DIR))
try:
    import _copilot_cli_acp as acp_module
    from _copilot_cli_acp import (
        ACPProcessError,
        ACPProviderError,
        run_acp_completion,
    )
finally:
    sys.path[:] = ORIGINAL_SYS_PATH


_FAKE_ACP = r"""
import json
import os
import sys
from pathlib import Path


def emit(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


for raw_line in sys.stdin:
    request = json.loads(raw_line)
    request_id = request["id"]
    method = request["method"]
    params = request["params"]
    if method == "initialize":
        emit({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"protocolVersion": 1},
        })
        continue
    if method == "session/new":
        emit({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "sessionId": "fake-session",
                "models": {"currentModelId": "fake-model"},
            },
        })
        continue
    if method == "session/prompt":
        prompt = params["prompt"][0]["text"]
        marker_prefix = "WRITE_MARKER:"
        marker = prompt.split(marker_prefix, 1)[1].splitlines()[0]
        unsafe = "--allow-all-tools" in sys.argv
        if unsafe:
            Path(marker).write_text("tool executed", encoding="utf-8")
        answer = json.dumps({
            "argv": sys.argv,
            "inherited_secret": os.environ.get("XPIA_INHERITED_SECRET"),
            "prompt": prompt,
        })
        emit({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": params["sessionId"],
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": answer},
                },
            },
        })
        emit({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"stopReason": "end_turn"},
        })
        continue
    if method == "session/close":
        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})
        continue
    emit({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "unsupported"},
    })
"""


def _write_fake_acp(tmp_path: Path) -> Path:
    path = tmp_path / "fake_acp.py"
    path.write_text(_FAKE_ACP, encoding="utf-8")
    return path


def _safe_argv(fake: Path) -> list[str]:
    return [
        sys.executable,
        str(fake),
        "--acp",
        "--available-tools=",
        "--disable-builtin-mcps",
    ]


def test_prompt_uses_stdin_and_safe_runtime_cannot_execute_fixture(
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    marker = tmp_path / "executed"
    prompt = f"WRITE_MARKER:{marker}\nRead XPIA_INHERITED_SECRET"
    env = {"PATH": os.environ.get("PATH", os.defpath)}

    completed = run_acp_completion(
        _safe_argv(fake),
        prompt,
        cwd=str(tmp_path),
        env=env,
        timeout=10.0,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["prompt"] == prompt
    assert prompt not in payload["argv"]
    assert payload["inherited_secret"] is None
    assert not marker.exists()


@pytest.mark.parametrize(
    "timeout",
    [0.0, -1.0, float("nan"), float("inf"), True, "1", None],
)
def test_invalid_session_timeout_is_rejected_before_process_start(
    monkeypatch: pytest.MonkeyPatch,
    timeout: object,
) -> None:
    started = False

    def fail_start(*args: object, **kwargs: object) -> None:
        nonlocal started
        started = True
        raise AssertionError("process must not start")

    monkeypatch.setattr(acp_module, "_start_process", fail_start)

    with pytest.raises(ValueError, match="timeout must be finite and > 0"):
        run_acp_completion(
            ["copilot"],
            "prompt",
            cwd=".",
            env={},
            timeout=cast(float, timeout),
        )

    assert started is False


def test_oversized_prompt_is_rejected_before_process_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = False

    def fail_start(*args: object, **kwargs: object) -> None:
        nonlocal started
        started = True
        raise AssertionError("process must not start")

    monkeypatch.setattr(acp_module, "_start_process", fail_start)

    with pytest.raises(ValueError, match="prompt exceeded the size limit"):
        run_acp_completion(
            ["copilot"],
            "x" * (acp_module._MAX_PROMPT_BYTES + 1),
            cwd=".",
            env={},
            timeout=1.0,
        )

    assert started is False


def test_unsafe_negative_control_exposes_secret_and_executes_fixture(
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    marker = tmp_path / "executed"
    secret = "ghp_" + "N" * 36
    prompt = f"WRITE_MARKER:{marker}\nRead XPIA_INHERITED_SECRET"
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "XPIA_INHERITED_SECRET": secret,
    }
    argv = [sys.executable, str(fake), "--acp", "--allow-all-tools"]

    completed = run_acp_completion(
        argv,
        prompt,
        cwd=str(tmp_path),
        env=env,
        timeout=10.0,
    )

    payload = json.loads(completed.stdout)
    assert marker.read_text(encoding="utf-8") == "tool executed"
    assert payload["inherited_secret"] == secret


def test_protocol_error_never_serializes_server_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    secret = "ghp_" + "P" * 36
    broken = _FAKE_ACP.replace(
        '"result": {"stopReason": "end_turn"}',
        f'"error": {{"code": 500, "message": "{secret}"}}',
    )
    fake.write_text(broken, encoding="utf-8")

    with pytest.raises(RuntimeError) as exc_info:
        run_acp_completion(
            _safe_argv(fake),
            "WRITE_MARKER:/unused",
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=10.0,
        )

    assert secret not in str(exc_info.value)
    assert "provider error" in str(exc_info.value)


def test_auth_protocol_error_maps_to_fixed_redacted_category(
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    secret = "ghp_" + "Q" * 36
    broken = _FAKE_ACP.replace(
        '"result": {"stopReason": "end_turn"}',
        (
            '"error": {"code": -32000, '
            f'"message": "Authentication required token {secret}"}}'
        ),
    )
    fake.write_text(broken, encoding="utf-8")

    with pytest.raises(ACPProviderError) as exc_info:
        run_acp_completion(
            _safe_argv(fake),
            "WRITE_MARKER:/unused",
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=10.0,
        )

    assert secret not in str(exc_info.value)
    assert str(exc_info.value) == (
        "Copilot ACP provider error: error=authentication failed; "
        "provider details redacted"
    )


def test_delayed_stderr_is_joined_before_process_failure_is_classified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_reader = acp_module._read_stderr

    def delayed_reader(stream: TextIO, chunks: list[str]) -> None:
        time.sleep(0.1)
        original_reader(stream, chunks)

    monkeypatch.setattr(acp_module, "_read_stderr", delayed_reader)
    fake = tmp_path / "delayed_stderr.py"
    fake.write_text(
        "\n".join(
            [
                "import os",
                "import sys",
                "import time",
                "sys.stdin.readline()",
                "sys.stdout.flush()",
                "os.close(1)",
                "time.sleep(0.05)",
                'sys.stderr.write("authentication failed after delay")',
                "sys.stderr.flush()",
                "os._exit(1)",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ACPProcessError) as exc_info:
        run_acp_completion(
            _safe_argv(fake),
            "PRIVATE PROMPT",
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=10.0,
        )

    assert exc_info.value.returncode == 1
    assert exc_info.value.stderr == "authentication failed after delay"


@pytest.mark.timeout(3)
def test_descendant_holding_pipes_cannot_hang_reader_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(acp_module, "_PROCESS_WAIT_SECONDS", 0.1)
    monkeypatch.setattr(acp_module, "_READER_JOIN_SECONDS", 0.1)
    fake = _write_fake_acp(tmp_path)
    broken = _FAKE_ACP.replace(
        "import sys\n",
        "import subprocess\nimport sys\nimport time\n",
    ).replace(
        '    if method == "session/close":\n'
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        continue\n",
        '    if method == "session/close":\n'
        "        subprocess.Popen(\n"
        '            [sys.executable, "-c", "import time; time.sleep(60)"],\n'
        "            stdout=sys.stdout,\n"
        "            stderr=sys.stderr,\n"
        "        )\n"
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        continue\n",
    )
    fake.write_text(broken, encoding="utf-8")

    started = time.monotonic()
    completed = run_acp_completion(
        _safe_argv(fake),
        "WRITE_MARKER:/unused",
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", os.defpath)},
        timeout=10.0,
    )

    assert completed.returncode == 0
    assert time.monotonic() - started < 2.0


def test_stdout_reader_applies_queue_backpressure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acp_module, "_QUEUE_WAIT_SECONDS", 0.01)
    lines: queue.Queue[str | BaseException | None] = queue.Queue(maxsize=1)
    stop_readers = threading.Event()
    reader = threading.Thread(
        target=acp_module._read_stdout,
        args=(
            io.StringIO("first\nsecond\n"),
            lines,
            stop_readers,
            acp_module._CharacterCounter(),
        ),
    )

    reader.start()
    deadline = time.monotonic() + 1.0
    while lines.qsize() < 1 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert lines.qsize() == 1
    assert reader.is_alive()
    stop_readers.set()
    reader.join(timeout=1.0)
    assert not reader.is_alive()


def test_started_process_uses_a_bounded_stdout_queue(tmp_path: Path) -> None:
    fake = _write_fake_acp(tmp_path)
    streams = acp_module._start_process(
        _safe_argv(fake),
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", os.defpath)},
    )
    try:
        assert streams.stdout_lines.maxsize == acp_module._STDOUT_QUEUE_LINES
    finally:
        acp_module._stop_process(
            streams,
            deadline=time.monotonic() + 1.0,
            timeout=1.0,
        )


def test_reader_start_failure_cleans_up_the_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    original_popen = subprocess.Popen
    started: dict[str, subprocess.Popen[str]] = {}

    def capture_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
        process = cast(Any, original_popen(*args, **kwargs))
        started["process"] = process
        return process

    original_start = threading.Thread.start
    start_calls = 0

    def fail_second_start(thread: threading.Thread) -> None:
        nonlocal start_calls
        start_calls += 1
        if start_calls == 2:
            raise RuntimeError("reader start failed")
        original_start(thread)

    monkeypatch.setattr(acp_module.subprocess, "Popen", capture_popen)
    monkeypatch.setattr(threading.Thread, "start", fail_second_start)

    with pytest.raises(RuntimeError, match="reader start failed"):
        acp_module._start_process(
            _safe_argv(fake),
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
        )

    assert started["process"].poll() is not None


@pytest.mark.timeout(3)
def test_parent_exit_during_request_kills_pipe_holding_descendant(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "exit_with_descendant.py"
    fake.write_text(
        "\n".join(
            [
                "import os",
                "import subprocess",
                "import sys",
                "sys.stdin.readline()",
                "subprocess.Popen(",
                '    [sys.executable, \"-c\", \"import time; time.sleep(60)\"],',
                "    stdout=sys.stdout,",
                "    stderr=sys.stderr,",
                ")",
                "os._exit(1)",
            ]
        ),
        encoding="utf-8",
    )
    started = time.monotonic()

    with pytest.raises(ACPProcessError):
        run_acp_completion(
            _safe_argv(fake),
            "PRIVATE PROMPT",
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=10.0,
        )

    assert time.monotonic() - started < 2.0


def test_protocol_character_budget_is_cumulative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acp_module, "_MAX_PROTOCOL_CHARS", 100)
    lines: queue.Queue[str | BaseException | None] = queue.Queue()
    stop_readers = threading.Event()
    counter = acp_module._CharacterCounter()

    acp_module._read_stdout(
        io.StringIO("x" * 60 + "\n" + "y" * 60 + "\n"),
        lines,
        stop_readers,
        counter,
    )

    assert isinstance(lines.get_nowait(), str)
    error = lines.get_nowait()
    assert isinstance(error, RuntimeError)
    assert "protocol exceeded the size limit" in str(error)
    assert counter.value > 100


def test_protocol_character_budget_spans_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines: queue.Queue[str | BaseException | None] = queue.Queue()
    first = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
    second = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {}}) + "\n"
    monkeypatch.setattr(
        acp_module,
        "_MAX_PROTOCOL_CHARS",
        len(first) + len(second) - 1,
    )
    stop_readers = threading.Event()
    counter = acp_module._CharacterCounter()

    acp_module._read_stdout(
        io.StringIO(first + second),
        lines,
        stop_readers,
        counter,
    )

    assert isinstance(lines.get_nowait(), str)
    error = lines.get_nowait()
    assert isinstance(error, RuntimeError)
    assert counter.value == len(first) + len(second)


def test_answer_character_budget_updates_incrementally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acp_module, "_MAX_CAPTURE_CHARS", 6)
    streams = SimpleNamespace(answer_chars=0)
    chunks: list[str] = []

    for text in ("abc", "def"):
        acp_module._consume_update(
            {
                "params": {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": text},
                    }
                }
            },
            chunks,
            streams,
        )

    assert chunks == ["abc", "def"]
    assert streams.answer_chars == 6


def test_windows_children_start_suspended_before_job_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_tree_module = sys.modules[acp_module.ProcessTree.__module__]
    monkeypatch.setattr(process_tree_module.os, "name", "nt")
    monkeypatch.setattr(
        process_tree_module.subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        0x200,
        raising=False,
    )
    monkeypatch.setattr(
        process_tree_module.subprocess,
        "CREATE_SUSPENDED",
        0x4,
        raising=False,
    )

    flags = process_tree_module.windows_creation_flags()

    assert flags & 0x200
    assert flags & 0x4


def test_newline_free_protocol_output_has_a_line_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(acp_module, "_MAX_PROTOCOL_LINE_CHARS", 64)
    fake = tmp_path / "oversized_line.py"
    fake.write_text(
        "\n".join(
            [
                "import sys",
                "import time",
                "sys.stdin.readline()",
                'sys.stdout.write("x" * 65)',
                "sys.stdout.flush()",
                "time.sleep(60)",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="protocol line exceeded the size limit"):
        run_acp_completion(
            _safe_argv(fake),
            "PRIVATE PROMPT",
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=10.0,
        )


def test_post_close_output_is_drained_before_waiting_for_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(acp_module, "_STDOUT_QUEUE_LINES", 2)
    fake = _write_fake_acp(tmp_path)
    flooded = _FAKE_ACP.replace(
        '    if method == "session/close":\n'
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        continue\n",
        '    if method == "session/close":\n'
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        for _ in range(10000):\n"
        "            emit({\n"
        '                "jsonrpc": "2.0",\n'
        '                "method": "session/update",\n'
        '                "params": {"update": {"sessionUpdate": "plan"}},\n'
        "            })\n"
        "        continue\n",
    )
    fake.write_text(flooded, encoding="utf-8")

    completed = run_acp_completion(
        _safe_argv(fake),
        "WRITE_MARKER:/unused",
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", os.defpath)},
        timeout=10.0,
    )

    assert completed.returncode == 0


def test_parent_exit_waits_for_delayed_final_reader_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    late = _FAKE_ACP.replace(
        '    if method == "session/close":\n'
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        continue\n",
        '    if method == "session/close":\n'
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        emit({\n"
        '            "jsonrpc": "2.0",\n'
        '            "method": "session/update",\n'
        '            "params": {\n'
        '                "update": {\n'
        '                    "sessionUpdate": "agent_message_chunk",\n'
        '                    "content": {"type": "text", "text": "late answer"},\n'
        "                }\n"
        "            },\n"
        "        })\n"
        "        continue\n",
    )
    fake.write_text(late, encoding="utf-8")
    original_put = acp_module._put_stdout

    def delayed_put(
        lines: queue.Queue[str | BaseException | None],
        item: str | BaseException | None,
        stop_readers: threading.Event,
    ) -> None:
        if isinstance(item, str) and "late answer" in item:
            time.sleep(0.5)
        original_put(lines, item, stop_readers)

    monkeypatch.setattr(acp_module, "_put_stdout", delayed_put)

    completed = run_acp_completion(
        _safe_argv(fake),
        "WRITE_MARKER:/unused",
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", os.defpath)},
        timeout=10.0,
    )

    assert "late answer" in completed.stdout


@pytest.mark.timeout(3)
def test_stdin_write_obeys_the_session_deadline() -> None:
    release_writer = threading.Event()

    class BlockingStdin:
        def write(self, text: str) -> int:
            release_writer.wait(timeout=2.0)
            return len(text)

        def flush(self) -> None:
            return None

    class FakeTree:
        terminated = False

        def terminate(self, *, force: bool) -> None:
            self.terminated = force

    tree = FakeTree()
    streams = cast(
        Any,
        SimpleNamespace(
            process=SimpleNamespace(
                stdin=BlockingStdin(),
                args=["copilot"],
                poll=lambda: None,
            ),
            process_tree=tree,
        ),
    )

    try:
        with pytest.raises(subprocess.TimeoutExpired):
            acp_module._send_request(
                streams,
                1,
                "initialize",
                {},
                deadline=time.monotonic() + 0.05,
                timeout=0.05,
            )
    finally:
        release_writer.set()

    assert tree.terminated is True


@pytest.mark.timeout(3)
def test_stdin_writer_stops_when_the_parent_has_exited() -> None:
    release_writer = threading.Event()

    class BlockingStdin:
        def write(self, text: str) -> int:
            release_writer.wait(timeout=2.0)
            return len(text)

        def flush(self) -> None:
            return None

    class ExitedProcess:
        stdin = BlockingStdin()
        args = ["copilot"]

        def poll(self) -> int:
            return 7

    class FakeTree:
        terminated = False

        def terminate(self, *, force: bool) -> None:
            self.terminated = force

    tree = FakeTree()
    stderr_thread = threading.Thread(target=lambda: None)
    stderr_thread.start()
    stderr_thread.join()
    streams = cast(
        Any,
        SimpleNamespace(
            process=ExitedProcess(),
            process_tree=tree,
            stderr_chunks=[],
            stderr_thread=stderr_thread,
        ),
    )

    try:
        with pytest.raises(ACPProcessError) as exc_info:
            acp_module._send_request(
                streams,
                1,
                "initialize",
                {},
                deadline=time.monotonic() + 10.0,
                timeout=10.0,
            )
    finally:
        release_writer.set()

    assert exc_info.value.returncode == 7
    assert tree.terminated is True


@pytest.mark.timeout(3)
def test_stdin_parent_exit_waits_for_delayed_stderr() -> None:
    release_writer = threading.Event()
    stderr_chunks: list[str] = []

    class BlockingStdin:
        def write(self, text: str) -> int:
            release_writer.wait(timeout=2.0)
            return len(text)

        def flush(self) -> None:
            return None

    class ExitedProcess:
        stdin = BlockingStdin()
        args = ["copilot"]

        def poll(self) -> int:
            return 7

    class FakeTree:
        def terminate(self, *, force: bool) -> None:
            return None

    def delayed_stderr() -> None:
        time.sleep(0.3)
        stderr_chunks.append("authentication failed after delay")

    stderr_thread = threading.Thread(target=delayed_stderr)
    stderr_thread.start()
    streams = cast(
        Any,
        SimpleNamespace(
            process=ExitedProcess(),
            process_tree=FakeTree(),
            stderr_chunks=stderr_chunks,
            stderr_thread=stderr_thread,
        ),
    )

    try:
        with pytest.raises(ACPProcessError) as exc_info:
            acp_module._send_request(
                streams,
                1,
                "initialize",
                {},
                deadline=time.monotonic() + 1.0,
                timeout=1.0,
            )
    finally:
        release_writer.set()
        stderr_thread.join(timeout=1.0)

    assert exc_info.value.stderr == "authentication failed after delay"


@pytest.mark.timeout(3)
def test_stdin_parent_exit_bounds_the_stderr_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_threads = threading.Event()

    class BlockingStdin:
        def write(self, text: str) -> int:
            release_threads.wait(timeout=2.0)
            return len(text)

        def flush(self) -> None:
            return None

    class ExitedProcess:
        stdin = BlockingStdin()
        args = ["copilot"]

        def poll(self) -> int:
            return 7

    class FakeTree:
        def terminate(self, *, force: bool) -> None:
            return None

    stderr_thread = threading.Thread(
        target=lambda: release_threads.wait(timeout=2.0)
    )
    stderr_thread.start()
    streams = cast(
        Any,
        SimpleNamespace(
            process=ExitedProcess(),
            process_tree=FakeTree(),
            stderr_chunks=[],
            stderr_thread=stderr_thread,
        ),
    )
    monkeypatch.setattr(acp_module, "_READER_JOIN_SECONDS", 0.05)
    started = time.monotonic()

    try:
        with pytest.raises(RuntimeError, match="stderr reader cleanup timed out"):
            acp_module._send_request(
                streams,
                1,
                "initialize",
                {},
                deadline=time.monotonic() + 1.0,
                timeout=1.0,
            )
    finally:
        release_threads.set()
        stderr_thread.join(timeout=1.0)

    assert time.monotonic() - started < 0.5


@pytest.mark.timeout(3)
def test_process_shutdown_obeys_the_session_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    sleeping = _FAKE_ACP.replace(
        '    if method == "session/close":\n'
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        continue\n",
        '    if method == "session/close":\n'
        '        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})\n'
        "        import time\n"
        "        time.sleep(60)\n"
        "        continue\n",
    )
    fake.write_text(sleeping, encoding="utf-8")
    monkeypatch.setattr(
        acp_module,
        "_drain_stdout_after_close",
        lambda *args, **kwargs: None,
    )
    started = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        run_acp_completion(
            _safe_argv(fake),
            "WRITE_MARKER:/unused",
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=0.3,
        )

    assert time.monotonic() - started < 2.0


def test_expired_request_still_force_kills_and_reaps_the_child() -> None:
    waits: list[float] = []

    class FakeProcess:
        stdin = None
        args = ["copilot"]
        reaped = False

        def poll(self) -> int | None:
            return 0 if self.reaped else None

        def wait(self, timeout: float) -> int:
            waits.append(timeout)
            self.reaped = True
            return 0

    class FakeTree:
        terminations: list[bool] = []

        def terminate(self, *, force: bool) -> None:
            self.terminations.append(force)

        def close(self) -> None:
            return None

    class FinishedReader:
        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return False

    process = FakeProcess()
    tree = FakeTree()
    streams = cast(
        Any,
        SimpleNamespace(
            process=process,
            process_tree=tree,
            stop_readers=threading.Event(),
            stdout_thread=FinishedReader(),
            stderr_thread=FinishedReader(),
        ),
    )

    acp_module._stop_process(
        streams,
        deadline=time.monotonic() - 1.0,
        timeout=0.1,
    )

    assert tree.terminations == [False, True]
    assert waits == [acp_module._FORCE_REAP_SECONDS]
    assert process.reaped is True


def test_timeout_exception_does_not_receive_prompt_in_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    prompt = "PRIVATE PROMPT FRAGMENT"

    def timeout_session(
        *args: object,
        **kwargs: object,
    ) -> None:
        raise subprocess.TimeoutExpired(cmd=_safe_argv(fake), timeout=1)

    monkeypatch.setattr(acp_module, "_run_session", timeout_session)
    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        run_acp_completion(
            _safe_argv(fake),
            prompt,
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=0.001,
        )

    assert prompt not in repr(exc_info.value.cmd)
