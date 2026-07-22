#!/usr/bin/env python3
"""Tests for the Claude-side hook group runner (#3075).

Covers: gate short-circuit and fail-closed semantics, gate_all and observe
modes, single-JSON output merging (the concatenation hazard that sank the
earlier ad hoc dispatcher), stdin replay, stdout.buffer capture, the
invoke_dispatch_claude.py entry point (unknown group, plugin self-host bail), and
a runtime-contract subprocess check with negative control.
"""

from __future__ import annotations

import io
import json
import ntpath
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = str(REPO_ROOT / ".claude" / "lib")
HOOKS_DIR = str(REPO_ROOT / ".claude" / "hooks")
for search_path in (LIB_DIR, HOOKS_DIR):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

import claude_hook_dispatch as chd  # noqa: E402
import claude_hook_protocol as protocol  # noqa: E402
import invoke_dispatch_claude as entry  # noqa: E402


def test_module_bootstrap_adds_lib_directory(monkeypatch):
    lib_dir = str(Path(chd.__file__).resolve().parent)
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if entry != lib_dir])

    runpy.run_path(chd.__file__, run_name="claude_hook_dispatch_bootstrap_probe")

    assert lib_dir in sys.path


def _write_shim(directory: Path, name: str, body: str) -> str:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return name


def _run(capsys, directory: Path, event: str, mode: str, shims: list[str], stdin: bytes = b"{}"):
    code = chd.run_group(directory, event, mode, shims, stdin)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- gate mode --------------------------------------------------------------


def test_gate_all_allow_silent(tmp_path, capsys):
    shims = [_write_shim(tmp_path, "a.py", "pass"), _write_shim(tmp_path, "b.py", "pass")]
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    assert out == ""


def test_gate_merges_context_json_into_single_document(tmp_path, capsys):
    body = (
        "import json\n"
        "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
        " 'additionalContext': %r}}))\n"
    )
    shims = [
        _write_shim(tmp_path, "a.py", body % "alpha guidance"),
        _write_shim(tmp_path, "b.py", body % "beta guidance"),
    ]
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    doc = json.loads(out)
    context = doc["hookSpecificOutput"]["additionalContext"]
    assert "alpha guidance" in context
    assert "beta guidance" in context
    assert doc["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_gate_merges_plain_text_as_context(tmp_path, capsys):
    shims = [
        _write_shim(tmp_path, "a.py", "print('plain alpha')"),
        _write_shim(tmp_path, "b.py", "print('plain beta')"),
    ]
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    doc = json.loads(out)
    context = doc["hookSpecificOutput"]["additionalContext"]
    assert "plain alpha" in context and "plain beta" in context


def test_gate_short_circuits_on_block_and_skips_later_shims(tmp_path, capsys):
    marker = tmp_path / "ran-later"
    shims = [
        _write_shim(
            tmp_path,
            "deny.py",
            "import sys\nprint('block guidance')\nsys.exit(2)\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n",
        ),
    ]
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 2
    assert "block guidance" in out
    assert not marker.exists()


def test_gate_nonblocking_error_does_not_skip_later_block(tmp_path, capsys):
    marker = tmp_path / "later-block-ran"
    shims = [
        _write_shim(tmp_path, "error.py", "raise SystemExit(1)\n"),
        _write_shim(
            tmp_path,
            "block.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            "raise SystemExit(2)\n",
        ),
    ]

    code, _, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 2
    assert marker.exists()
    assert "error.py exited 1" in err


def test_gate_preserves_nonblocking_error_after_later_allow(tmp_path, capsys):
    marker = tmp_path / "later-allow-ran"
    shims = [
        _write_shim(tmp_path, "error.py", "raise SystemExit(1)\n"),
        _write_shim(
            tmp_path,
            "allow.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            "print('later context')\n",
        ),
    ]

    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 1
    assert marker.exists()
    assert "later context" in out


@pytest.mark.parametrize(
    ("event", "mode", "decision"),
    [
        (
            "PreToolUse",
            chd.GATE,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "blocked",
                }
            },
        ),
        ("Stop", chd.GATE_ALL, {"decision": "block", "reason": "blocked"}),
    ],
)
def test_nonblocking_error_does_not_override_later_decision(
    tmp_path,
    capsys,
    event,
    mode,
    decision,
):
    shims = [
        _write_shim(tmp_path, "error.py", "raise SystemExit(1)\n"),
        _write_shim(
            tmp_path,
            "block.py",
            f"import json\nprint(json.dumps({decision!r}))\n",
        ),
    ]

    code, out, _ = _run(capsys, tmp_path, event, mode, shims)

    assert code == 0
    assert json.loads(out) == decision


def test_gate_decision_json_is_terminal_and_verbatim(tmp_path, capsys):
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "no",
        }
    }
    marker = tmp_path / "ran-later"
    shims = [
        _write_shim(
            tmp_path,
            "deny_json.py",
            f"import json\nprint(json.dumps({decision!r}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n",
        ),
    ]
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    assert json.loads(out) == decision
    assert not marker.exists()


def test_gate_continue_false_is_terminal_and_verbatim(tmp_path, capsys):
    decision = {"continue": False, "stopReason": "stop now"}
    marker = tmp_path / "ran-later"
    shims = [
        _write_shim(
            tmp_path,
            "stop.py",
            f"import json\nprint(json.dumps({decision!r}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 0
    assert json.loads(out) == decision
    assert not marker.exists()
    assert err == ""


@pytest.mark.parametrize(
    "document",
    [
        {"decision": "bogus"},
        {"decision": "allow", "reason": "skip siblings"},
        {"permissionDecision": "deny"},
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        },
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
            }
        },
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "futureField": "value",
            }
        },
        {"continue": True},
        {"continue": False, "stopReason": None},
        {"continue": False, "systemMessage": 7},
        {"hookSpecificOutput": None},
        {"hookSpecificOutput": 7},
        {"hookSpecificOutput": []},
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": None,
            }
        },
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "blocked",
                "additionalContext": None,
            }
        },
        {"systemMessage": 7},
        {"suppressOutput": "yes"},
        {
            "suppressOutput": "yes",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "blocked",
            },
        },
    ],
)
def test_gate_invalid_structured_output_fails_closed(tmp_path, capsys, document):
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(
            tmp_path,
            "invalid.py",
            f"import json\nprint(json.dumps({document!r}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 2
    assert out == ""
    assert not marker.exists()
    assert "invalid or unsupported structured output" in err


@pytest.mark.parametrize(
    "stdout",
    [
        '{"decision":',
        '{"hookSpecificOutput":{"hookEventName":"PreToolUse"',
        '{"continue":false} trailing',
    ],
)
def test_gate_malformed_json_object_fails_closed(tmp_path, capsys, stdout):
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(tmp_path, "malformed.py", f"print({stdout!r})\n"),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 2
    assert out == ""
    assert not marker.exists()
    assert "invalid or unsupported structured output" in err


def test_gate_missing_shim_fails_closed(tmp_path, capsys):
    code, _, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, ["absent.py"])
    assert code == 2
    assert "missing on disk" in err


def test_gate_raising_shim_fails_closed(tmp_path, capsys):
    shims = [_write_shim(tmp_path, "boom.py", "raise RuntimeError('kaput')")]
    code, _, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 2
    assert "kaput" in err


# --- gate_all mode ----------------------------------------------------------


@pytest.mark.parametrize("exit_codes", [(1, 2), (2, 1)])
def test_gate_all_runs_every_shim_and_propagates_block(
    tmp_path,
    capsys,
    exit_codes,
):
    marker = tmp_path / "ran-later"
    shims = [
        _write_shim(
            tmp_path,
            "first.py",
            f"raise SystemExit({exit_codes[0]})\n",
        ),
        _write_shim(
            tmp_path,
            "second.py",
            f"raise SystemExit({exit_codes[1]})\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n"
            "print('later ran')\n",
        ),
    ]
    code, out, _ = _run(capsys, tmp_path, "UserPromptSubmit", chd.GATE_ALL, shims)
    assert code == 2
    assert marker.exists()
    assert "later ran" in out


def test_gate_all_plain_context_events_emit_plain_text(tmp_path, capsys):
    shims = [
        _write_shim(tmp_path, "a.py", "print('first note')"),
        _write_shim(tmp_path, "b.py", "print('second note')"),
    ]
    code, out, _ = _run(capsys, tmp_path, "UserPromptSubmit", chd.GATE_ALL, shims)
    assert code == 0
    assert "first note" in out and "second note" in out
    with pytest.raises(ValueError):
        json.loads(out)


@pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
def test_gate_all_valid_stop_decision_runs_later_shims(tmp_path, capsys, event):
    decision = {"decision": "block", "reason": "work remains"}
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(
            tmp_path,
            "block.py",
            f"import json\nprint(json.dumps({decision!r}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, event, chd.GATE_ALL, shims)

    assert code == 0
    assert json.loads(out) == decision
    assert marker.exists()
    assert err == ""


@pytest.mark.parametrize(
    ("event", "mode", "document", "later_runs"),
    [
        (
            "PreToolUse",
            chd.GATE,
            {"decision": "block", "reason": "wrong event"},
            False,
        ),
        (
            "Stop",
            chd.GATE_ALL,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "wrong event",
                }
            },
            True,
        ),
    ],
)
def test_wrong_event_blocker_fails_closed(
    tmp_path, capsys, event, mode, document, later_runs
):
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(
            tmp_path,
            "invalid.py",
            f"import json\nprint(json.dumps({document!r}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, event, mode, shims)

    assert code == 2
    assert out == ""
    assert marker.exists() == later_runs
    assert "invalid or unsupported structured output" in err


def test_gate_all_missing_shim_blocks_but_continues(tmp_path, capsys):
    shims = [
        "absent.py",
        _write_shim(tmp_path, "b.py", "print('still ran')"),
    ]
    code, out, err = _run(capsys, tmp_path, "Stop", chd.GATE_ALL, shims)
    assert code == 2
    assert "still ran" in out
    assert "missing on disk" in err


def test_gate_all_nonzero_shim_preserves_context(tmp_path, capsys):
    shims = [
        _write_shim(
            tmp_path,
            "partial.py",
            "print('partial guidance')\nraise SystemExit(1)\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "Stop", chd.GATE_ALL, shims)

    assert code == 1
    assert out.strip() == "partial guidance"
    assert "partial.py exited 1" in err


def test_gate_all_logs_second_decision_and_keeps_first(tmp_path, capsys):
    shims = [
        _write_shim(
            tmp_path,
            "first.py",
            "import json\nprint(json.dumps({'decision': 'block', 'reason': 'first'}))\n",
        ),
        _write_shim(
            tmp_path,
            "second.py",
            "import json\nprint(json.dumps({'decision': 'block', 'reason': 'second'}))\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "Stop", chd.GATE_ALL, shims)

    assert code == 0
    assert json.loads(out)["reason"] == "first"
    assert "second decision document" in err
    assert '"reason": "second"' in err


def test_gate_all_invalid_output_overrides_earlier_nonblocking_error(
    tmp_path,
    capsys,
):
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(tmp_path, "error.py", "raise SystemExit(1)\n"),
        _write_shim(
            tmp_path,
            "invalid.py",
            "import json\n"
            "print(json.dumps({'decision': 'allow', 'reason': 'invalid'}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, _, err = _run(capsys, tmp_path, "Stop", chd.GATE_ALL, shims)

    assert code == 2
    assert marker.exists()
    assert "invalid or unsupported structured output" in err


# --- observe mode -----------------------------------------------------------


def test_observe_never_blocks(tmp_path, capsys):
    shims = [
        _write_shim(tmp_path, "deny.py", "import sys\nsys.exit(2)\n"),
        _write_shim(tmp_path, "b.py", "print('observer note')"),
    ]
    code, out, _ = _run(capsys, tmp_path, "SessionStart", chd.OBSERVE, shims)
    assert code == 0
    assert "observer note" in out


def test_observe_suppresses_invalid_structured_output(tmp_path, capsys):
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(tmp_path, "invalid.py", "print('{\"systemMessage\": 7}')\n"),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "SessionStart", chd.OBSERVE, shims)

    assert code == 0
    assert out == ""
    assert marker.exists()
    assert "suppressing in observe mode" in err


def test_observe_suppresses_valid_blocking_document(tmp_path, capsys):
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(
            tmp_path,
            "decision.py",
            "import json\nprint(json.dumps({'continue': False, 'stopReason': 'stop'}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "SessionStart", chd.OBSERVE, shims)

    assert code == 0
    assert out == ""
    assert marker.exists()
    assert "suppressing decision in observe mode" in err


def test_unknown_mode_fails_closed(tmp_path, capsys):
    code, _, err = _run(capsys, tmp_path, "PreToolUse", "bogus", [])
    assert code == 2
    assert "invalid group contract" in err


def test_empty_group_fails_closed(tmp_path, capsys):
    code, _, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, [])
    assert code == 2
    assert "group shims must not be empty" in err


@pytest.mark.parametrize(
    "shims",
    [
        ["a.py", "a.py"],
        ["Guard.py", "guard.py"],
        ["/absolute.py"],
        ["../escape.py"],
        [r"nested\escape.py"],
        ["not-python.sh"],
    ],
)
def test_validate_group_rejects_unsafe_shim_entries(shims):
    with pytest.raises(ValueError):
        chd.validate_group("PreToolUse", chd.GATE, shims)


def test_validate_group_rejects_nonlist_shims():
    with pytest.raises(TypeError, match="group shims must be a list"):
        chd.validate_group("PreToolUse", chd.GATE, ("guard.py",))


def test_hooks_directory_resolution_error_fails_closed(tmp_path, monkeypatch, capsys):
    name = _write_shim(tmp_path, "guard.py", "pass\n")
    real_realpath = chd.os.path.realpath

    def fail_hooks_directory(path):
        if Path(path) == tmp_path:
            raise OSError("hooks directory unavailable")
        return real_realpath(path)

    monkeypatch.setattr(chd.os.path, "realpath", fail_hooks_directory)

    code, _, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, [name])

    assert code == 2
    assert "hooks directory cannot be resolved" in err
    assert "hooks directory unavailable" in err


def test_shim_resolution_error_fails_closed(tmp_path, monkeypatch, capsys):
    name = _write_shim(tmp_path, "broken.py", "pass\n")
    real_realpath = chd.os.path.realpath

    def fail_broken_path(path):
        if Path(path).name == name:
            raise OSError("resolution failed")
        return real_realpath(path)

    monkeypatch.setattr(chd.os.path, "realpath", fail_broken_path)

    code, _, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, [name])

    assert code == 2
    assert "registered shim path is unsafe" in err
    assert "resolution failed" in err


def test_resolved_shim_escape_fails_closed(tmp_path, monkeypatch, capsys):
    error = _write_shim(tmp_path, "error.py", "raise SystemExit(1)\n")
    name = _write_shim(tmp_path, "escape.py", "pass\n")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    real_realpath = chd.os.path.realpath
    outside_resolved = real_realpath(outside)

    def escape_hooks_directory(path):
        if Path(path).name == name:
            return outside_resolved
        return real_realpath(path)

    monkeypatch.setattr(chd.os.path, "realpath", escape_hooks_directory)

    code, _, err = _run(
        capsys,
        tmp_path,
        "Stop",
        chd.GATE_ALL,
        [error, name],
    )

    assert code == 2
    assert "registered shim path is unsafe" in err


def test_gate_all_unsafe_shim_sets_block_and_continues(tmp_path, monkeypatch, capsys):
    marker = tmp_path / "later-ran"
    name = _write_shim(tmp_path, "escape.py", "pass\n")
    later = _write_shim(
        tmp_path,
        "later.py",
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
    )
    outside = tmp_path.parent / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    real_realpath = chd.os.path.realpath
    outside_resolved = real_realpath(outside)

    def escape_hooks_directory(path):
        if Path(path).name == name:
            return outside_resolved
        return real_realpath(path)

    monkeypatch.setattr(chd.os.path, "realpath", escape_hooks_directory)

    code, _, err = _run(
        capsys,
        tmp_path,
        "Stop",
        chd.GATE_ALL,
        [name, later],
    )

    assert code == 2
    assert marker.exists()
    assert "registered shim path is unsafe" in err


def test_observe_unsafe_and_missing_shims_log_and_continue(tmp_path, monkeypatch, capsys):
    marker = tmp_path / "later-ran"
    unsafe = _write_shim(tmp_path, "unsafe.py", "pass\n")
    later = _write_shim(
        tmp_path,
        "later.py",
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
    )
    outside = tmp_path.parent / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    real_realpath = chd.os.path.realpath
    outside_resolved = real_realpath(outside)

    def escape_hooks_directory(path):
        if Path(path).name == unsafe:
            return outside_resolved
        return real_realpath(path)

    monkeypatch.setattr(chd.os.path, "realpath", escape_hooks_directory)

    code, _, err = _run(
        capsys,
        tmp_path,
        "SessionStart",
        chd.OBSERVE,
        [unsafe, "missing.py", later],
    )

    assert code == 0
    assert marker.exists()
    assert "registered shim path is unsafe" in err
    assert "registered shim missing on disk: missing.py" in err


def test_path_containment_rejects_sibling_prefix(tmp_path):
    hooks_dir = tmp_path / "hooks"
    sibling_shim = tmp_path / "hooks-copy" / "shim.py"

    assert not chd._is_path_within(sibling_shim, hooks_dir)


def test_path_containment_normalizes_windows_case_and_drive(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(chd.os.path, "normcase", ntpath.normcase)
        patch.setattr(chd.os.path, "commonpath", ntpath.commonpath)

        assert chd._is_path_within(
            Path(r"C:\Repo\Hooks\shim.py"),
            Path(r"c:\repo\hooks"),
        )
        assert not chd._is_path_within(
            Path(r"D:\Repo\Hooks\shim.py"),
            Path(r"c:\repo\hooks"),
        )


@pytest.mark.parametrize(
    ("event", "mode", "expected_code"),
    [
        ("PreToolUse", chd.GATE, 2),
        ("Stop", chd.GATE_ALL, 2),
        ("SessionStart", chd.OBSERVE, 0),
    ],
)
def test_resolved_shim_alias_cannot_run_twice(
    tmp_path,
    monkeypatch,
    capsys,
    event,
    mode,
    expected_code,
):
    count = tmp_path / "count"
    error = _write_shim(tmp_path, "error.py", "raise SystemExit(1)\n")
    target = _write_shim(
        tmp_path,
        "target.py",
        "from pathlib import Path\n"
        f"p = Path({str(count)!r})\n"
        "p.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\n",
    )
    alias = _write_shim(tmp_path, "alias.py", "pass\n")
    real_realpath = chd.os.path.realpath
    target_resolved = real_realpath(tmp_path / target)

    def resolve_alias(path):
        if Path(path).name == alias:
            return target_resolved
        return real_realpath(path)

    monkeypatch.setattr(chd.os.path, "realpath", resolve_alias)

    code, _, err = _run(
        capsys,
        tmp_path,
        event,
        mode,
        [error, target, alias],
    )

    assert code == expected_code
    assert count.read_text(encoding="utf-8") == "1"
    assert "resolves to duplicate target" in err


# --- stdin / stdout mechanics ----------------------------------------------


def test_each_shim_sees_full_stdin(tmp_path, capsys):
    body = "import sys\ndata = sys.stdin.read()\nprint(f'saw:{len(data)}')\n"
    shims = [
        _write_shim(tmp_path, "a.py", body),
        _write_shim(tmp_path, "b.py", body),
    ]
    payload = b'{"tool_name": "Bash", "tool_input": {"command": "echo"}}'
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims, stdin=payload)
    assert code == 0
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert context.count(f"saw:{len(payload)}") == 2


def test_stdout_buffer_writes_are_captured(tmp_path, capsys):
    body = "import sys\nsys.stdout.buffer.write(b'bytes note')\nsys.stdout.flush()\n"
    shims = [_write_shim(tmp_path, "a.py", body)]
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    assert "bytes note" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize(
    "body",
    [
        "import os\nos.write(1, b'fd note\\n')\n",
        (
            "import subprocess, sys\n"
            "subprocess.run(\n"
            "    [sys.executable, '-c', \"print('child note')\"],\n"
            "    check=True,\n"
            ")\n"
        ),
    ],
)
def test_fd_and_child_stdout_are_merged_into_one_document(tmp_path, capfd, body):
    shims = [
        _write_shim(tmp_path, "a.py", body),
        _write_shim(tmp_path, "b.py", "print('normal note')\n"),
    ]

    code, out, _ = _run(capfd, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 0
    doc = json.loads(out)
    context = doc["hookSpecificOutput"]["additionalContext"]
    assert "note" in context
    assert "normal note" in context


def test_shim_can_import_sibling_companion_module(tmp_path, capsys):
    # Standalone execution puts the script's directory on sys.path[0];
    # the dispatcher must preserve that contract or shims with sibling
    # companion modules fail with ModuleNotFoundError and block the
    # event (observed live).
    _write_shim(tmp_path, "Sub/companion_mod.py", "VALUE = 'companion-ok'\n")
    shims = [
        _write_shim(
            tmp_path,
            "Sub/owner.py",
            "import companion_mod\nprint(companion_mod.VALUE)\n",
        )
    ]
    code, out, _ = _run(capsys, tmp_path, "Stop", chd.GATE_ALL, shims)
    assert code == 0
    assert "companion-ok" in out
    assert str(tmp_path / "Sub") not in sys.path


def test_stdin_restored_after_run(tmp_path, capsys):
    saved = sys.stdin
    shims = [_write_shim(tmp_path, "a.py", "pass")]
    _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert sys.stdin is saved


def test_argv_and_path_mutations_do_not_leak_between_shims(tmp_path, capsys):
    record = tmp_path / "state.json"
    poisoned_path = str(tmp_path / "poisoned")
    shims = [
        _write_shim(
            tmp_path,
            "mutate.py",
            "import sys\n"
            f"sys.path.insert(0, {poisoned_path!r})\n"
            "sys.argv.append('poisoned-argument')\n",
        ),
        _write_shim(
            tmp_path,
            "record.py",
            "import json, sys\n"
            "from pathlib import Path\n"
            f"Path({str(record)!r}).write_text(json.dumps({{"
            "'argv': sys.argv, "
            f"'poisoned_path': {poisoned_path!r} in sys.path"
            "}))\n",
        ),
    ]

    code, _, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 0, err
    state = json.loads(record.read_text(encoding="utf-8"))
    assert state["argv"] == [str(tmp_path / "record.py")]
    assert state["poisoned_path"] is False


# --- output classification --------------------------------------------------


@pytest.mark.parametrize(
    ("stdout_text", "expected_context", "expected_decision"),
    [
        ("", None, None),
        ("plain words", "plain words", None),
        ('{"decision": "block", "reason": "r"}', None, '{"decision": "block", "reason": "r"}'),
        ('{"continue": false}', None, '{"continue": false}'),
        (
            '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "ctx"}}',
            "ctx",
            None,
        ),
        ("[1, 2]", "[1, 2]", None),
        ('{"systemMessage": "warn text"}', "warn text", None),
        ('{"suppressOutput": true}', None, None),
        ('{"systemMessage": "warn", "suppressOutput": true}', "warn", None),
        (
            '{"hookSpecificOutput": {"hookEventName": "PostToolUse", '
            '"additionalContext": "wrong event"}}',
            None,
            '{"hookSpecificOutput": {"hookEventName": "PostToolUse", '
            '"additionalContext": "wrong event"}}',
        ),
        (
            '{"hookSpecificOutput": {"hookEventName": "PreToolUse", '
            '"additionalContext": "  "}}',
            None,
            None,
        ),
    ],
)
def test_classify_stdout(stdout_text, expected_context, expected_decision):
    context, decision, _recognized = chd._classify_stdout(stdout_text, "PreToolUse")
    assert context == expected_context
    if expected_decision is None:
        assert decision is None
    else:
        assert decision is not None
        assert json.loads(decision) == json.loads(expected_decision)


def test_blocking_document_rejects_invalid_common_fields():
    document = {
        "continue": False,
        "stopReason": "stop",
        "systemMessage": 7,
    }

    assert not protocol._is_valid_blocking_document(document, "Stop")


def test_standalone_system_message_does_not_terminate_gate_group(tmp_path, capsys):
    # The LSP guards emit {"systemMessage": ...} on their warn path; that
    # advisory document must never skip later gates in the group.
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(
            tmp_path,
            "warn.py",
            "import json\nprint(json.dumps({'systemMessage': 'lsp warn'}))\n",
        ),
        _write_shim(
            tmp_path,
            "later.py",
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n",
        ),
    ]
    code, out, _ = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    assert marker.exists()
    assert "lsp warn" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_unrecognized_json_becomes_context_and_is_warned(tmp_path, capsys):
    shims = [
        _write_shim(
            tmp_path,
            "debug.py",
            "import json\nprint(json.dumps({'error': 'timeout'}))\n",
        ),
    ]
    code, out, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == '{"error": "timeout"}'
    assert "no recognized protocol keys" in err
    assert "treating it as context and continuing" in err


def test_unrecognized_json_cannot_skip_a_later_gate(tmp_path, capsys):
    marker = tmp_path / "later-ran"
    shims = [
        _write_shim(
            tmp_path,
            "debug.py",
            "import json\nprint(json.dumps({'error': 'timeout'}))\n",
        ),
        _write_shim(
            tmp_path,
            "block.py",
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit(2)\n",
        ),
    ]

    code, out, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)

    assert code == 2
    assert marker.exists()
    assert out == ""
    assert "treating it as context and continuing" in err


def test_gate_all_blocking_shim_decision_document_logged_to_stderr(tmp_path, capsys):
    shims = [
        _write_shim(
            tmp_path,
            "blockdoc.py",
            "import json, sys\nprint(json.dumps({'decision': 'block', 'reason': 'r'}))\n"
            "sys.exit(2)\n",
        ),
    ]
    code, out, err = _run(capsys, tmp_path, "Stop", chd.GATE_ALL, shims)
    assert code == 2
    assert '"decision"' not in out
    assert "decision document" in err and "block" in err


# --- invoke_dispatch_claude.py entry ----------------------------------------------


def _entry_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env["AI_AGENTS_PROJECT_REPO"] = "1"
    if extra:
        env.update(extra)
    return env


def _write_dispatch_manifest(hooks_dir: Path, group: object) -> None:
    hooks_dir.mkdir()
    (hooks_dir / "dispatch_groups.json").write_text(
        json.dumps({"groups": {"test-group": group}}),
        encoding="utf-8",
    )


def test_load_group_accepts_reviewed_contract(tmp_path, monkeypatch):
    hooks_dir = tmp_path / "hooks"
    group = {
        "event": "PreToolUse",
        "mode": "gate",
        "shims": [{"file": "PreToolUse/guard.py"}],
    }
    _write_dispatch_manifest(hooks_dir, group)
    monkeypatch.setattr(entry, "_HOOKS_DIR", hooks_dir)

    assert entry._load_group("test-group") == (
        "PreToolUse",
        "gate",
        ["PreToolUse/guard.py"],
    )


def test_entry_runtime_exception_fails_closed(monkeypatch, capsys):
    monkeypatch.setattr(entry, "_project_self_hosts_plugin", lambda: False)
    monkeypatch.setattr(
        entry,
        "_load_group",
        lambda _group_id: ("PreToolUse", chd.GATE, ["guard.py"]),
    )

    def fail_runtime(*_args, **_kwargs):
        raise RuntimeError("runtime failed")

    monkeypatch.setattr(entry, "run_group", fail_runtime)
    monkeypatch.setattr(entry.sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}")))

    code = entry.main(["--group", "test-group"])

    assert code == 2
    assert "runtime failed" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [(chd.GATE, 2), (chd.GATE_ALL, 2), (chd.OBSERVE, 0)],
)
def test_entry_bounds_stdin_by_dispatch_mode(
    monkeypatch,
    capsys,
    mode,
    expected_code,
):
    monkeypatch.setattr(entry, "_project_self_hosts_plugin", lambda: False)
    monkeypatch.setattr(
        entry,
        "_load_group",
        lambda _group_id: (
            "SessionStart" if mode == chd.OBSERVE else "PreToolUse",
            mode,
            ["guard.py"],
        ),
    )
    monkeypatch.setattr(entry, "_MAX_STDIN_BYTES", 8)
    monkeypatch.setattr(
        entry.sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(b"123456789")),
    )
    ran = False

    def record_run(*_args, **_kwargs):
        nonlocal ran
        ran = True
        return 0

    monkeypatch.setattr(entry, "run_group", record_run)

    assert entry.main(["--group", "test-group"]) == expected_code
    assert ran is False
    assert "stdin exceeds 8 bytes" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module_body", "expected_error"),
    [
        ("raise RuntimeError('bootstrap failed')\n", b"bootstrap failed"),
        ("raise SystemExit(0)\n", b"SystemExit: 0"),
        ("raise SystemExit(1)\n", b"SystemExit: 1"),
    ],
)
def test_entry_import_failure_exits_two(tmp_path, module_body, expected_error):
    hooks_dir = tmp_path / "hooks"
    lib_dir = tmp_path / "lib"
    hooks_dir.mkdir()
    lib_dir.mkdir()
    script = hooks_dir / "invoke_dispatch_claude.py"
    script.write_text(
        (REPO_ROOT / ".claude" / "hooks" / script.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (lib_dir / "claude_hook_dispatch.py").write_text(
        module_body,
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-u", str(script), "--group", "test-group"],
        input=b"{}",
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 2
    assert b"entrypoint initialization failed" in result.stderr
    assert expected_error in result.stderr


def test_entry_self_host_check_exception_fails_closed(monkeypatch, capsys):
    def fail_preflight():
        raise OSError("project directory unavailable")

    monkeypatch.setattr(entry, "_project_self_hosts_plugin", fail_preflight)

    code = entry.main(["--group", "test-group"])

    assert code == 2
    err = capsys.readouterr().err
    assert "self-host check failed" in err
    assert "project directory unavailable" in err


def test_entry_manifest_exception_fails_closed(monkeypatch, capsys):
    monkeypatch.setattr(entry, "_project_self_hosts_plugin", lambda: False)

    def fail_manifest(_group_id):
        raise RuntimeError("manifest loader failed")

    monkeypatch.setattr(entry, "_load_group", fail_manifest)

    code = entry.main(["--group", "test-group"])

    assert code == 2
    err = capsys.readouterr().err
    assert "cannot load group" in err
    assert "manifest loader failed" in err


@pytest.mark.parametrize(
    "group",
    [
        {"event": "PreToolUse", "mode": "gate", "shims": []},
        {"event": "PreToolUse", "mode": "gate", "shims": "guard.py"},
        {"event": "PreToolUse", "mode": "gate", "shims": ["guard.py"]},
        {"event": "PreToolUse", "mode": "gate", "shims": [{}]},
        {
            "event": "PreToolUse",
            "mode": "gate",
            "shims": [{"file": "../guard.py"}],
        },
        {
            "event": "PreToolUse",
            "mode": "gate",
            "shims": [{"file": "C:guard.py"}],
        },
        {
            "event": "SessionStart",
            "mode": "gate",
            "shims": [{"file": "SessionStart/observer.py"}],
        },
        {
            "event": "UnknownEvent",
            "mode": "observe",
            "shims": [{"file": "observer.py"}],
        },
        {
            "event": 7,
            "mode": "gate",
            "shims": [{"file": "PreToolUse/guard.py"}],
        },
    ],
)
def test_load_group_rejects_malformed_contract(tmp_path, monkeypatch, group):
    hooks_dir = tmp_path / "hooks"
    _write_dispatch_manifest(hooks_dir, group)
    monkeypatch.setattr(entry, "_HOOKS_DIR", hooks_dir)

    with pytest.raises((TypeError, ValueError)):
        entry._load_group("test-group")


def test_entry_empty_group_fails_closed(tmp_path, monkeypatch, capsys):
    hooks_dir = tmp_path / "hooks"
    _write_dispatch_manifest(
        hooks_dir,
        {"event": "PreToolUse", "mode": "gate", "shims": []},
    )
    monkeypatch.setattr(entry, "_HOOKS_DIR", hooks_dir)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

    assert entry.main(["--group", "test-group"]) == 2
    assert "group shims must not be empty" in capsys.readouterr().err


def test_entry_unknown_group_fails_loud():
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            ".claude/hooks/invoke_dispatch_claude.py",
            "--group",
            "no-such-group",
        ],
        cwd=REPO_ROOT,
        env=_entry_env(),
        input=b"{}",
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2
    assert b"no-such-group" in result.stderr


def test_entry_plugin_self_host_bails_fast(tmp_path):
    # Simulate the installed plugin running inside the repo that publishes
    # it: CLAUDE_PLUGIN_ROOT points at this repo's .claude tree and the
    # project dir is the repo itself.
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            ".claude/hooks/invoke_dispatch_claude.py",
            "--group",
            "no-such-group",
        ],
        cwd=REPO_ROOT,
        env=_entry_env(
            {
                "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT / ".claude"),
                "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
            }
        ),
        input=b"{}",
        capture_output=True,
        timeout=60,
        check=False,
    )
    # Bail happens before group resolution, so even a bogus group allows.
    assert result.returncode == 0
    assert result.stdout == b""


def test_entry_plugin_outside_publisher_repo_runs(tmp_path):
    # Same plugin root, but the project dir is a plain consumer directory:
    # the dispatcher must NOT bail (and then fails loud on the bogus group).
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            ".claude/hooks/invoke_dispatch_claude.py",
            "--group",
            "no-such-group",
        ],
        cwd=REPO_ROOT,
        env=_entry_env(
            {
                "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT / ".claude"),
                "CLAUDE_PROJECT_DIR": str(tmp_path),
            }
        ),
        input=b"{}",
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2


# --- runtime contract (real group, real shims, real payload) ----------------


def test_runtime_contract_context_group_allows():
    # Real manifest and real context-loader shim must allow session start.
    payload = json.dumps({}).encode("utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            ".claude/hooks/invoke_dispatch_claude.py",
            "--group",
            "sessionstart-1-session_initialization_enforcer",
        ],
        cwd=REPO_ROOT,
        env=_entry_env(),
        input=payload,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
