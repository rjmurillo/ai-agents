#!/usr/bin/env python3
"""Tests for the Claude-side hook group runner (#3075).

Covers: gate short-circuit and fail-closed semantics, gate_all and observe
modes, single-JSON output merging (the concatenation hazard that sank the
earlier ad hoc dispatcher), stdin replay, stdout.buffer capture, the
invoke_dispatch_claude.py entry point (unknown group, plugin self-host bail), and
a runtime-contract subprocess check with negative control.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = str(REPO_ROOT / ".claude" / "lib")
HOOKS_DIR = str(REPO_ROOT / ".claude" / "hooks")
for entry in (LIB_DIR, HOOKS_DIR):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import claude_hook_dispatch as chd  # noqa: E402


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


def test_gate_all_runs_every_shim_and_propagates_block(tmp_path, capsys):
    marker = tmp_path / "ran-later"
    shims = [
        _write_shim(tmp_path, "deny.py", "import sys\nsys.exit(2)\n"),
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


def test_gate_all_missing_shim_blocks_but_continues(tmp_path, capsys):
    shims = [
        "absent.py",
        _write_shim(tmp_path, "b.py", "print('still ran')"),
    ]
    code, out, err = _run(capsys, tmp_path, "Stop", chd.GATE_ALL, shims)
    assert code == 2
    assert "still ran" in out
    assert "missing on disk" in err


# --- observe mode -----------------------------------------------------------


def test_observe_never_blocks(tmp_path, capsys):
    shims = [
        _write_shim(tmp_path, "deny.py", "import sys\nsys.exit(2)\n"),
        _write_shim(tmp_path, "b.py", "print('observer note')"),
    ]
    code, out, _ = _run(capsys, tmp_path, "SessionStart", chd.OBSERVE, shims)
    assert code == 0
    assert "observer note" in out


def test_unknown_mode_fails_closed(tmp_path, capsys):
    code, _, err = _run(capsys, tmp_path, "PreToolUse", "bogus", [])
    assert code == 2
    assert "unknown mode" in err


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
    ],
)
def test_classify_stdout(stdout_text, expected_context, expected_decision):
    context, decision, _recognized = chd._classify_stdout(stdout_text)
    assert context == expected_context
    if expected_decision is None:
        assert decision is None
    else:
        assert decision is not None
        assert json.loads(decision) == json.loads(expected_decision)


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


def test_unrecognized_json_is_terminal_but_warned(tmp_path, capsys):
    shims = [
        _write_shim(
            tmp_path,
            "debug.py",
            "import json\nprint(json.dumps({'error': 'timeout'}))\n",
        ),
    ]
    code, out, err = _run(capsys, tmp_path, "PreToolUse", chd.GATE, shims)
    assert code == 0
    assert json.loads(out) == {"error": "timeout"}
    assert "no recognized protocol keys" in err


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


def test_runtime_contract_prompt_group_allows():
    # Real manifest, real shims: the UserPromptSubmit group is advisory
    # and must allow a benign prompt (plain-text context on stdout).
    payload = json.dumps({"prompt": "hello"}).encode("utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            ".claude/hooks/invoke_dispatch_claude.py",
            "--group",
            "userpromptsubmit-1-serena_reassertion",
        ],
        cwd=REPO_ROOT,
        env=_entry_env(),
        input=payload,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_runtime_contract_branch_mismatch_blocks_via_push_group(tmp_path):
    # Negative control: a git push issued from a branch that does not match the
    # session log's recorded branch must be blocked through the push-chain
    # group, proving group members really execute under the live manifest and a
    # member's exit-2 block propagates out of the real dispatch entry point.
    #
    # branch_context_guard (the group's first shim) keys off the *current*
    # branch of the resolved project directory versus the branch recorded in
    # today's session log. A detached-HEAD checkout (CI's PR merge-commit
    # checkout, or a --detach worktree) reports no current branch, so the guard
    # fails open and the control becomes vacuous. Point CLAUDE_PROJECT_DIR at a
    # scratch repo on `main` with a session log that expects a different branch
    # so the guard deterministically fires.
    on_main = tmp_path / "on-main"
    on_main.mkdir()
    subprocess.run(
        ["git", "init", str(on_main)], check=True, capture_output=True, timeout=30
    )
    subprocess.run(
        ["git", "-C", str(on_main), "checkout", "-B", "main"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    # An unborn HEAD (branch created, no commit) makes `git branch
    # --show-current` return an empty string on some git versions, which would
    # let branch_context_guard fail open and reintroduce the very
    # non-determinism this negative control exists to remove. A single empty
    # commit gives HEAD a born ref so the branch name resolves deterministically.
    subprocess.run(
        [
            "git",
            "-C",
            str(on_main),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    # A today-dated session log whose recorded branch differs from the scratch
    # repo's current branch (`main`) is what branch_context_guard blocks on.
    sessions_dir = on_main / ".agents" / "sessions"
    sessions_dir.mkdir(parents=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    (sessions_dir / f"{today}-session-01.json").write_text(
        json.dumps({"session": {"branch": "feature/mismatch"}}), encoding="utf-8"
    )
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
    ).encode("utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            ".claude/hooks/invoke_dispatch_claude.py",
            "--group",
            "pretooluse-2-branch_context_guard",
        ],
        cwd=REPO_ROOT,
        env=_entry_env({"CLAUDE_PROJECT_DIR": str(on_main)}),
        input=payload,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 2, result.stderr.decode(errors="replace")
