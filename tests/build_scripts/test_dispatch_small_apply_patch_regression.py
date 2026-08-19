#!/usr/bin/env python3
"""Regression guard for issue #3083 (Copilot host-versus-direct-replay code 1).

Also guards issues #3203 and #3321 (freeform ``apply_patch`` denied by the
plugin's PreToolUse gate) via the string-``tool_input`` fixtures below.

On Windows the Copilot CLI host reported ``Hook command failed with code 1`` on a
small ``apply_patch`` PreToolUse payload, yet a direct replay of the same payload
through ``_dispatch.py`` returned exit 0. No PreToolUse shim matches
``apply_patch``: the committed manifest registers a single ``Bash``-scoped
markdownlint guard, and the broader shim set it replaced carried no
``apply_patch`` matcher either. Every shim skips and the dispatcher returns
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
``apply_patch`` (see the shim list in
``src/copilot-cli/hooks/PreToolUse/_manifest.json``), so every guard skips and
the dispatcher allows. If a future
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

# Issues #3203 and #3321: the host delivers a freeform patch as a raw V4A STRING
# in tool_input, not an object, and it reached the retired Write/Edit security
# gate under both the apply_patch name and the Edit name. That gate required a
# dict and denied (#3203); #3204 taught it to parse the string; #3295 retired the
# gate and narrowed the host matcher to Bash. These fixtures carry the #3321
# reproduction bytes (an *** Add File: header with an absolute Windows path to a
# nested Markdown file) so a future guard that reintroduces a dict-only
# tool_input assumption fails here instead of in a consumer's session.
_WINDOWS_ADD_FILE_PATCH = (
    "*** Begin Patch\n"
    "*** Add File: C:\\Users\\op\\repo\\.agentlog\\feat-x\\copilot-cli\\workflow.md\n"
    "+# Workflow\n"
    "*** End Patch\n"
)
_FREEFORM_STRING_EVENT: dict[str, object] = {
    "tool_name": "apply_patch",
    "tool_input": _WINDOWS_ADD_FILE_PATCH,
}
_FREEFORM_EDIT_STRING_EVENT: dict[str, object] = {
    "tool_name": "Edit",
    "tool_input": _WINDOWS_ADD_FILE_PATCH,
}
# The concrete #3321 denial mechanism on plugin versions 0.6.66 through 0.6.97:
# the retired gate treated EVERY column-0 ``***`` line it could not attribute to
# a path as a malformed header and failed closed, so the standard V4A
# ``*** End of File`` marker denied the whole patch. Replaying that exact byte
# sequence against 8318d1c350^ reproduces
# "tool_input carries malformed patch header(s)... : *** End of File" (exit 2);
# the same bytes exit 0 here.
_FREEFORM_END_OF_FILE_EVENT: dict[str, object] = {
    "tool_name": "Edit",
    "tool_input": (
        "*** Begin Patch\n"
        "*** Add File: C:\\Users\\op\\repo\\.agentlog\\feat-x\\copilot-cli\\workflow.md\n"
        "+# Workflow\n"
        "*** End of File\n"
        "*** End Patch\n"
    ),
}


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
    [
        _RECORDED_HOST_EVENT,
        _NORMALIZED_EVENT,
        _FREEFORM_STRING_EVENT,
        _FREEFORM_EDIT_STRING_EVENT,
        _FREEFORM_END_OF_FILE_EVENT,
    ],
    ids=[
        "recorded-host-event",
        "normalized-tool-name",
        "freeform-patch-string",
        "freeform-patch-string-as-edit",
        "freeform-patch-end-of-file-marker",
    ],
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


def test_oversized_matched_payload_denies_with_context(tmp_path: Path) -> None:
    # Issue #5154 retired the Bash(git push*) group this used to exercise. The
    # property is unchanged: a payload that MATCHES a registered shim and
    # exceeds the replay limit denies, and the message names the matcher, the
    # source field, and the limit. Only the matching payload shape moved.
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "E" * (_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES + 1)},
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(raw) > _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES

    proc = _run_dispatch(raw, _PLUGIN_ROOT, tmp_path)

    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 2
    assert "^(Agent|Task)$" in stderr
    assert "tool_input" in stderr
    assert str(_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES) in stderr
    for stream in (proc.stdout, proc.stderr):
        assert b"E" * 4096 not in stream


def test_harness_observes_nonzero_exit(tmp_path: Path) -> None:
    # Teeth for the positive assertion: point the plugin root at a directory that
    # is not a plugin so the bootstrap detects infrastructure failure. Post-fix
    # (issue 4672), infrastructure failure fails OPEN (exit 0 with warning) rather
    # than closed (exit 2). This still proves the subprocess harness surfaces the
    # correct exit code, so ``assert rc == 0`` above is not vacuous.
    raw = json.dumps(_RECORDED_HOST_EVENT).encode("utf-8")

    proc = _run_dispatch(raw, tmp_path, tmp_path)

    assert proc.returncode == 0, (
        f"expected fail-open exit 0 from a non-plugin root (issue 4672), "
        f"got {proc.returncode}"
    )
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert "WARNING: hooks DISABLED" in stderr, (
        "infrastructure failure must emit a warning on stderr"
    )
