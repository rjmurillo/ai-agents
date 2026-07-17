"""Security tests for matcher-shim JSON and alias canonicalization."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

from generate_hooks import inject_shim  # noqa: E402

_ECHO_SCRIPT = (
    "import json\n"
    "import sys\n"
    "data = json.load(sys.stdin)\n"
    "print(json.dumps(data, sort_keys=True), flush=True)\n"
)


def _run_shim_raw(
    transformed_source: str, raw_input: bytes
) -> subprocess.CompletedProcess[bytes]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(transformed_source)
        path = handle.name
    try:
        return subprocess.run(
            [sys.executable, path],
            input=raw_input,
            capture_output=True,
            timeout=15,
        )
    finally:
        os.unlink(path)


def _run_shim(
    transformed_source: str, payload: dict[str, Any]
) -> subprocess.CompletedProcess[bytes]:
    return _run_shim_raw(
        transformed_source,
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )


def _run_committed_git_push_shim(raw_input: bytes) -> subprocess.CompletedProcess[bytes]:
    matches = list(
        (REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse").glob(
            "invoke_branch_context_guard__Bash_git_push_*.py"
        )
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one committed git-push shim, found {matches}")
    env = dict(os.environ)
    env["COPILOT_PLUGIN_ROOT"] = str(REPO_ROOT / "src" / "copilot-cli")
    return subprocess.run(
        [sys.executable, str(matches[0])],
        input=raw_input,
        capture_output=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=15,
    )


def test_conflicting_input_aliases_fail_closed_before_matching():
    transformed = inject_shim(_ECHO_SCRIPT, "Bash(git push*)")
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo safe"},
        "toolArgs": {"command": "git push origin main"},
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert b"conflicting top-level tool_input/toolArgs values" in proc.stderr
    assert proc.stdout == b""


def test_matching_aliases_replay_one_canonical_schema():
    transformed = inject_shim(_ECHO_SCRIPT, "Bash(git push*)")
    tool_input = {"command": "git push origin main"}
    payload = {
        "sessionId": "matching-aliases",
        "tool_name": "Bash",
        "toolName": "Bash",
        "tool_input": tool_input,
        "toolArgs": json.dumps(tool_input),
        "tool_call_id": "call-1",
        "toolCallId": "call-1",
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 0, proc.stderr.decode()
    assert json.loads(proc.stdout) == {
        "sessionId": "matching-aliases",
        "tool_call_id": "call-1",
        "tool_input": tool_input,
        "tool_name": "Bash",
    }


def test_boolean_and_number_input_aliases_fail_closed():
    transformed = inject_shim(_ECHO_SCRIPT, "^Edit$")
    payload = {
        "tool_name": "Edit",
        "tool_input": {"line": 1},
        "toolArgs": {"line": True},
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert b"conflicting top-level tool_input/toolArgs values" in proc.stderr
    assert proc.stdout == b""


def test_boolean_and_number_call_id_aliases_fail_closed():
    transformed = inject_shim(_ECHO_SCRIPT, "^Edit$")
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "README.md"},
        "tool_call_id": 1,
        "toolCallId": True,
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert b"conflicting top-level tool_call_id/toolCallId values" in proc.stderr
    assert proc.stdout == b""


def test_conflicting_call_id_aliases_fail_closed():
    transformed = inject_shim(_ECHO_SCRIPT, "^Edit$")
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "README.md"},
        "tool_call_id": "snake-id",
        "toolCallId": "camel-id",
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert b"conflicting top-level tool_call_id/toolCallId values" in proc.stderr
    assert proc.stdout == b""


def test_duplicate_top_level_toolcalls_keys_fail_closed():
    transformed = inject_shim(_ECHO_SCRIPT, "^Edit$")
    raw = (
        b'{"toolCalls":[{"name":"Edit","args":{"file_path":"README.md"}}],'
        b'"toolCalls":[]}'
    )

    proc = _run_shim_raw(transformed, raw)

    assert proc.returncode == 2
    assert b"duplicate JSON object key" in proc.stderr
    assert proc.stdout == b""


def test_duplicate_nested_call_keys_fail_closed():
    transformed = inject_shim(_ECHO_SCRIPT, "^Edit$")
    raw = (
        b'{"toolCalls":[{"name":"Read","name":"Edit",'
        b'"args":{"file_path":"README.md"}}]}'
    )

    proc = _run_shim_raw(transformed, raw)

    assert proc.returncode == 2
    assert b"duplicate JSON object key" in proc.stderr
    assert proc.stdout == b""


def test_duplicate_keys_in_encoded_toolargs_fail_closed():
    transformed = inject_shim(_ECHO_SCRIPT, "Bash(git push*)")
    payload = {
        "toolName": "Bash",
        "toolArgs": (
            '{"command":"echo safe","command":"git push origin main"}'
        ),
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 2
    assert b"duplicate JSON object key" in proc.stderr
    assert proc.stdout == b""


def test_camel_case_payload_replays_as_snake_case():
    transformed = inject_shim(_ECHO_SCRIPT, "^Edit$")
    payload = {
        "toolName": "Edit",
        "toolArgs": '{"file_path":"README.md"}',
        "toolCallId": "call-2",
    }

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 0, proc.stderr.decode()
    assert json.loads(proc.stdout) == {
        "tool_call_id": "call-2",
        "tool_input": {"file_path": "README.md"},
        "tool_name": "Edit",
    }


def test_committed_shim_rejects_conflicting_input_aliases():
    raw = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "echo safe"},
            "toolArgs": {"command": "git push origin main"},
        },
        separators=(",", ":"),
    ).encode("utf-8")

    proc = _run_committed_git_push_shim(raw)

    assert proc.returncode == 2
    assert b"conflicting top-level tool_input/toolArgs values" in proc.stderr


def test_committed_shim_rejects_duplicate_toolcalls_keys():
    raw = (
        b'{"toolCalls":[{"name":"Bash","args":{"command":"git push"}}],'
        b'"toolCalls":[]}'
    )

    proc = _run_committed_git_push_shim(raw)

    assert proc.returncode == 2
    assert b"duplicate JSON object key" in proc.stderr


def _nested_json_overflowing_stdin() -> bytes:
    """Return JSON bytes whose nesting overflows this interpreter's parser.

    The exact depth that trips ``RecursionError`` in the stdlib JSON C
    scanner depends on the C stack size, which varies by platform and Python
    build. Probe upward until the local parser raises, then reuse those bytes:
    the shim runs under the same interpreter, so the same depth overflows
    there too. This keeps the test deterministic across environments instead
    of hard-coding a depth that might parse cleanly on a larger stack.
    Refs issue #3169.
    """
    depth = 200_000
    while depth <= 5_000_000:
        payload = b"[" * depth + b"0" + b"]" * depth
        try:
            json.loads(payload)
        except RecursionError:
            return payload
        depth *= 2
    pytest.skip("could not induce a JSON RecursionError in this interpreter")


def _run_committed_pretooluse_dispatcher(
    raw_input: bytes,
) -> subprocess.CompletedProcess[bytes]:
    dispatcher = (
        REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse" / "_dispatch.py"
    )
    if not dispatcher.exists():
        raise AssertionError(f"committed dispatcher missing: {dispatcher}")
    env = dict(os.environ)
    env["COPILOT_PLUGIN_ROOT"] = str(REPO_ROOT / "src" / "copilot-cli")
    return subprocess.run(
        [sys.executable, str(dispatcher)],
        input=raw_input,
        capture_output=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=30,
    )


def test_deeply_nested_json_fails_closed_direct_shim():
    # Issue #3169: a standalone shim (run directly, not under the dispatcher)
    # must fail closed on deeply nested JSON that raises RecursionError inside
    # the parser, rather than leaking exit 1 and a full traceback. RecursionError
    # is not a ValueError subclass, so it escaped the malformed-JSON handler.
    transformed = inject_shim(_ECHO_SCRIPT, "Bash(git push*)")

    proc = _run_shim_raw(transformed, _nested_json_overflowing_stdin())

    assert proc.returncode == 2, proc.stderr.decode()
    assert b"stdin JSON nesting too deep" in proc.stderr
    assert b"Traceback" not in proc.stderr
    assert b"RecursionError" not in proc.stderr
    assert len(proc.stderr) < 512
    assert proc.stdout == b""


def test_shallow_json_still_parses_direct_shim():
    # Negative control: nesting below the overflow threshold parses normally and
    # does not trip the fail-closed path, so the RecursionError catch adds no
    # false positives for well-formed input.
    transformed = inject_shim(_ECHO_SCRIPT, "Bash(git push*)")
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo safe"}}

    proc = _run_shim(transformed, payload)

    assert proc.returncode == 0, proc.stderr.decode()
    assert b"nesting too deep" not in proc.stderr


def test_committed_shim_rejects_deeply_nested_json():
    proc = _run_committed_git_push_shim(_nested_json_overflowing_stdin())

    assert proc.returncode == 2, proc.stderr.decode()
    assert b"stdin JSON nesting too deep" in proc.stderr
    assert b"Traceback" not in proc.stderr
    assert len(proc.stderr) < 4096


def test_committed_dispatcher_rejects_deeply_nested_json():
    # Dispatcher negative control: the production dispatcher already fails closed
    # on RecursionError. This guards against regressing that path while fixing
    # the standalone shim (issue #3169).
    proc = _run_committed_pretooluse_dispatcher(_nested_json_overflowing_stdin())

    assert proc.returncode == 2, proc.stderr.decode()
    assert b"Traceback" not in proc.stderr
