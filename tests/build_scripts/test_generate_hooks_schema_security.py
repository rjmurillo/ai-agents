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


def _run_committed_shim(
    raw_input: bytes, name_contains: str = "invoke_require_subagent_model"
) -> subprocess.CompletedProcess[bytes]:
    """Run one shipped PreToolUse matcher shim against raw stdin.

    This used to name the ``Bash(git push*)`` markdownlint shim. Issue #5154
    retired it, leaving ``require_subagent_model`` as the sole survivor, so
    the default target became whatever matcher shim the tree actually ships.
    Two amendments then each added a second shim, both dated 2026-08-18:
    issue #5061 added ``serena_memory_scope_guard``, and issue #4917 added
    ``serena_worktree_scope_guard`` (registered as group 12, renumbered up
    from its own branch's `-11-` suffix to avoid colliding with #5061's
    already-landed group 11). Both new shims commit to a DIFFERENT
    malformed-input policy than ``require_subagent_model``'s: they fail
    closed on stdin too large to parse safely, where
    ``require_subagent_model`` fails open (#4672). The callers of this
    helper document and assert `require_subagent_model`'s specific fail-open
    policy, not "whatever the one shim is", so globbing alone is no longer
    unambiguous with three shims on the tree. ``name_contains`` pins the
    target explicitly; a missing match still fails loudly rather than
    silently picking the wrong shim's policy.
    """
    matches = sorted(
        path
        for path in (REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse").glob(
            "invoke_*__*.py"
        )
        if name_contains in path.name
    )
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one committed matcher shim matching "
            f"{name_contains!r}, found {matches}"
        )
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

    proc = _run_committed_shim(raw)

    # The shipped require_subagent_model shim detects the conflict and refuses
    # to hand it to the guard. It exits 0 rather than 2 because that shim
    # matches on tool NAME: an unusable payload cannot be shown to be an Agent
    # spawn, so the shim skips instead of denying (#4672 fail-open policy, and
    # the guard's own docstring: it bounds model spend and is not a security
    # boundary). serena_memory_scope_guard (issue #5061, merged 2026-08-19)
    # has a different policy for its own scope-resolution failures, which is
    # why _run_committed_shim pins the target explicitly rather than globbing
    # for "the one shim" now that two exist. The fail-closed path for a
    # command-scoped matcher, which cannot rule out a push, is covered by
    # test_shim_rejects_conflicting_input_aliases above.
    assert proc.returncode == 0, proc.stderr.decode()
    assert b"conflicting top-level tool_input/toolArgs values" in proc.stderr
    assert b"Traceback" not in proc.stderr


def test_committed_shim_rejects_duplicate_toolcalls_keys():
    raw = (
        b'{"toolCalls":[{"name":"Bash","args":{"command":"git push"}}],'
        b'"toolCalls":[]}'
    )

    proc = _run_committed_shim(raw)

    # Exit 0 for the same reason as the aliases case above: this targets
    # require_subagent_model's specific #4672 fail-open policy.
    assert proc.returncode == 0, proc.stderr.decode()
    assert b"duplicate JSON object key" in proc.stderr
    assert b"Traceback" not in proc.stderr


def _nested_json_overflowing_stdin() -> bytes:
    """Return JSON bytes whose nesting overflows this interpreter's parser.

    The stdlib JSON C scanner raises ``RecursionError`` once nesting nears the
    interpreter's C-stack recursion guard. That depth tracks the C stack size,
    which varies by platform and Python build, so this probes for it at run
    time instead of hard-coding a very deep constant. A fixed large depth would
    build a needlessly deep payload on small-stack platforms (Windows, threaded
    runners) where the guard trips far sooner. Refs issue #3169.

    Two robustness details:

    * ``MemoryError`` (a payload too large to allocate or parse) skips the test
      rather than crashing the runner.
    * The returned depth is twice the minimal depth that overflows this probe.
      The probe runs deep inside pytest's call stack, so it hits the guard at a
      shallower nesting than the shim does when it parses the same bytes near
      the top of a fresh process. Doubling guarantees the shim overflows too,
      and it scales with the platform's measured limit instead of a hand-tuned
      constant.
    """

    def _overflows(candidate: int) -> bool:
        payload = b"[" * candidate + b"0" + b"]" * candidate
        try:
            json.loads(payload)
            return False
        except RecursionError:
            return True

    low = 0
    high = 0
    depth = 1_000
    ceiling = 2_000_000
    while depth <= ceiling:
        try:
            if _overflows(depth):
                high = depth
                break
            low = depth
        except MemoryError:
            pytest.skip("insufficient memory to induce a JSON RecursionError")
        depth *= 2
    if high == 0:
        pytest.skip("could not induce a JSON RecursionError in this interpreter")
    while high - low > 1:
        mid = (low + high) // 2
        try:
            if _overflows(mid):
                high = mid
            else:
                low = mid
        except MemoryError:
            pytest.skip("insufficient memory to induce a JSON RecursionError")
    safe_depth = high * 2
    return b"[" * safe_depth + b"0" + b"]" * safe_depth


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
    proc = _run_committed_shim(_nested_json_overflowing_stdin())

    # The property under test is that the SHIPPED artifact catches the
    # RecursionError, says so in a bounded message, and leaks no traceback.
    # Exit 0 is require_subagent_model's tool-name-matcher policy (see the
    # aliases test); _run_committed_shim pins that specific shim by name.
    assert proc.returncode == 0, proc.stderr.decode()
    assert b"stdin JSON nesting too deep" in proc.stderr
    assert b"Traceback" not in proc.stderr
    assert b"RecursionError" not in proc.stderr
    assert len(proc.stderr) < 4096


def test_committed_dispatcher_rejects_deeply_nested_json():
    # Dispatcher negative control: the production dispatcher already fails closed
    # on RecursionError. This guards against regressing that path while fixing
    # the standalone shim (issue #3169).
    proc = _run_committed_pretooluse_dispatcher(_nested_json_overflowing_stdin())

    # The dispatcher propagates its shims' verdicts, running every registered
    # shim in manifest order (gate mode) and stopping at the first nonzero
    # exit, per Decision point 4. The committed order is
    # require_subagent_model (group 10), serena_memory_scope_guard (group
    # 11, #5061), serena_worktree_scope_guard (group 12, #4917, renumbered
    # up from its own branch's `-11-` to avoid colliding with #5061's
    # already-landed group). require_subagent_model fails open on
    # unparseable stdin (#4672): it logs the detection and verdicts 0, as it
    # did alone in the brief #5154-only window. serena_memory_scope_guard's
    # own docstring commits it to failing CLOSED when "stdin payload was too
    # large to parse safely": a stray cross-worktree memory write cannot be
    # ruled out from unparseable input, so it logs the detection too and
    # verdicts nonzero, which stops the gate there. serena_worktree_scope_guard
    # is also documented fail-closed for the same case ("Fail-closed for
    # writes: If the session project root ... cannot be determined, write
    # tools are blocked"), but gate mode never reaches it: group 11's
    # nonzero exit already stopped the chain, so this test cannot observe
    # group 12's own policy for this input (see ADR-068 Decision point 2 on
    # the later-shim bypass). The aggregate verdict is 2, and exactly two
    # shims' detection messages appear (each bounded and traceback-free).
    assert proc.returncode == 2, proc.stderr.decode()
    assert proc.stderr.count(b"stdin JSON nesting too deep") == 2
    assert b"Traceback" not in proc.stderr
