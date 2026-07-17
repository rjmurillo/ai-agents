#!/usr/bin/env python3
"""Regression guard for issue #3083 (Copilot host-versus-direct-replay code 1).

On Windows the Copilot CLI host reported ``Hook command failed with code 1`` on a
small ``apply_patch`` PreToolUse payload, yet a direct replay of the same payload
through ``_dispatch.py`` returned exit 0. No PreToolUse shim matches
``apply_patch`` (the manifest carries Bash, Write/Edit, Grep, Glob, Read, Task,
and Agent shims), so on this payload every shim skips and the dispatcher returns
0. The dispatcher is not limited to {0, 2} in general: ``hook_dispatch.run_dispatch``
propagates a matching shim's first non-zero exit code, so a registered shim that
exited 1 would surface 1. It is the ABSENCE of an ``apply_patch`` matcher, not a
structural limit, that makes exit 1 impossible for THIS payload. The exit-1 the
host reported therefore originates in the Windows ``py -3`` host or launcher, not
the dispatcher. That host bug is external and stays open on #3083; we cannot fix a
Windows launcher from this repo.

What this preserves: the in-repo half of that discrepancy. It replays a small
``apply_patch`` payload through the SHIPPED, committed
``src/copilot-cli/hooks/PreToolUse/_dispatch.py`` under the verified plugin-root
contract and asserts exit 0. No registered PreToolUse shim matches
``apply_patch`` (the manifest carries Bash, Write/Edit, Grep, Glob, Read, Task,
and Agent shims), so every guard skips and the dispatcher allows. If a future
dispatcher change ever made this benign payload return a non-zero code, this
guard fails and localizes the regression to the dispatcher rather than the host.

This gates the committed artifact, not the generator (see
``.claude/rules/generated-artifacts.md``): it runs the real ``_dispatch.py`` as a
subprocess, the same way issue #3074's repro invoked
``py -3 -u "$root\\hooks\\PreToolUse\\_dispatch.py"``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO / "src" / "copilot-cli"
_DISPATCH = _PLUGIN_ROOT / "hooks" / "PreToolUse" / "_dispatch.py"

_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES = 2 * 1024 * 1024

# A small representative apply_patch payload, well under the matched replay
# limit. Its exact bytes do not matter because no matcher selects apply_patch.
# This is the Copilot host event shape: sessionId, cwd, and a
# toolCalls entry whose name is apply_patch. It carries no top-level tool_name,
# exactly as the recorded data.input did, so every matcher shim skips it.
_RECORDED_HOST_EVENT: dict[str, object] = {
    "sessionId": "regression-3083",
    "cwd": "consumer-repo",
    "toolCalls": [
        {
            "id": "call_apply_patch_1",
            "name": "apply_patch",
            "args": (
                "*** Begin Patch\n"
                "*** Update File: README.md\n"
                "@@\n"
                "-old text\n"
                "+new text\n"
                "*** End Patch\n"
            ),
        }
    ],
}

# Normalized hook shape: even when the dispatcher sees apply_patch as the tool
# name directly, no registered guard matches it, so it still allows. This ties
# the guard to apply_patch rather than to "any shape lacking tool_name".
_NORMALIZED_EVENT: dict[str, object] = {"tool_name": "apply_patch", "tool_input": {}}


def _run_dispatch(
    payload: bytes, plugin_root: Path, cwd: Path
) -> subprocess.CompletedProcess[bytes]:
    """Run the committed PreToolUse dispatcher under the plugin-root contract.

    Copilot launches a plugin hook from the user's cwd, not the plugin dir.
    The launcher chooses COPILOT_PLUGIN_ROOT with CLAUDE_PLUGIN_ROOT as its
    fallback, while the Python bootstrap consumes CLAUDE_PLUGIN_ROOT. Set both
    to the same install directory so this test covers either launcher input.
    """
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    env["COPILOT_PLUGIN_ROOT"] = str(plugin_root)
    return subprocess.run(
        [sys.executable, "-u", str(_DISPATCH)],
        input=payload,
        capture_output=True,
        cwd=str(cwd),
        env=env,
        timeout=60,
    )


@pytest.mark.parametrize(
    "payload",
    [_RECORDED_HOST_EVENT, _NORMALIZED_EVENT],
    ids=["recorded-host-event", "normalized-tool-name"],
)
def test_small_apply_patch_payload_allows(payload: dict[str, object], tmp_path: Path) -> None:
    raw = json.dumps(payload).encode("utf-8")
    assert len(raw) < _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES, (
        "fixture must stay under the matched replay limit"
    )

    proc = _run_dispatch(raw, _PLUGIN_ROOT, tmp_path)

    assert proc.returncode == 0, (
        f"the committed dispatcher denied a benign small apply_patch payload "
        f"(rc={proc.returncode}). The dispatcher must allow; the Windows host's "
        f"exit 1 is external (issue #3083).\n"
        f"{proc.stderr.decode('utf-8', errors='replace')[:600]}"
    )


def test_oversized_unmatched_apply_patch_payload_allows(tmp_path: Path) -> None:
    payload = {
        "sessionId": "regression-3074-unmatched",
        "cwd": "consumer-repo",
        "toolCalls": [
            {
                "id": "call_apply_patch_large",
                "name": "apply_patch",
                "args": "P" * (_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES + 1),
            }
        ],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(raw) > _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES

    proc = _run_dispatch(raw, _PLUGIN_ROOT, tmp_path)

    assert proc.returncode == 0, proc.stderr.decode(
        "utf-8", errors="replace"
    )
    assert b"P" * 4096 not in proc.stdout
    assert b"P" * 4096 not in proc.stderr


def test_oversized_matched_edit_payload_denies_with_context(tmp_path: Path) -> None:
    payload = {
        "sessionId": "regression-3074-matched",
        "cwd": "consumer-repo",
        "toolCalls": [
            {
                "id": "call_edit_large",
                "name": "Edit",
                "args": "E" * (_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES + 1),
            }
        ],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(raw) > _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES

    proc = _run_dispatch(raw, _PLUGIN_ROOT, tmp_path)

    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 2
    assert "^(Write|Edit)$" in stderr
    assert "toolCalls.args" in stderr
    assert str(_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES) in stderr
    for stream in (proc.stdout, proc.stderr):
        assert b"E" * 4096 not in stream


def test_harness_observes_nonzero_exit(tmp_path: Path) -> None:
    # Teeth for the positive assertion: point the plugin root at a directory that
    # is not a plugin so the bootstrap fails closed (exit 2). This proves the same
    # subprocess harness surfaces a non-zero exit, so ``assert rc == 0`` above is
    # not vacuous. It deliberately keeps the recorded payload small so this
    # negative control isolates bootstrap failure rather than payload size.
    raw = json.dumps(_RECORDED_HOST_EVENT).encode("utf-8")

    proc = _run_dispatch(raw, tmp_path, tmp_path)

    assert proc.returncode == 2, (
        f"expected fail-closed exit 2 from a non-plugin root, got {proc.returncode}; "
        f"the harness cannot observe non-zero exits, so the positive test lacks teeth"
    )
