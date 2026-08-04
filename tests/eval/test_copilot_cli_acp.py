"""Runtime-contract tests for the text-only Copilot ACP transport."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(EVAL_DIR))
try:
    from _copilot_cli_acp import run_acp_completion  # noqa: E402
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


def test_timeout_exception_does_not_receive_prompt_in_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _write_fake_acp(tmp_path)
    prompt = "PRIVATE PROMPT FRAGMENT"

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=_safe_argv(fake), timeout=1)

    monkeypatch.setattr(subprocess.Popen, "wait", timeout)
    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        run_acp_completion(
            _safe_argv(fake),
            prompt,
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", os.defpath)},
            timeout=0.001,
        )

    assert prompt not in repr(exc_info.value.cmd)
