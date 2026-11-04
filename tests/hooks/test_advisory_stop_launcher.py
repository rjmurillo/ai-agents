#!/usr/bin/env python3
"""Advisory Stop group behavior of the Claude hook launcher (REQ-048 AC-26, AC-27).

An advisory group is a ``Stop`` group registered with ``--advisory``. Two
behaviors are new, and both are scoped to it:

- AC-26: the hook's ``systemMessage`` leaves the launcher as a ``systemMessage``
  document, not as plain Stop stdout.
- AC-27: every launcher failure path exits 0 and writes one stderr status line.

Every test that proves an advisory behavior has a control that runs the same
input without ``advisory`` and asserts the old behavior, so other groups are
shown unchanged.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for search_path in (str(REPO_ROOT / ".claude" / "lib"), str(REPO_ROOT / ".claude" / "hooks")):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

import claude_hook_dispatch as chd
import invoke_dispatch_claude as entry

MESSAGE = "Consider running /retrospective."
EMIT_MESSAGE = f"import json\nprint(json.dumps({{'systemMessage': {MESSAGE!r}}}))\n"
BLOCK_DOC = {"decision": "block", "reason": "stop"}


def _shim(directory: Path, body: str, name: str = "Stop/s.py") -> list[str]:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return [name]


def _run(capsys: pytest.CaptureFixture[str], directory: Path, shims: list[str], **kw: bool):
    code = chd.run_group(directory, "Stop", chd.GATE_ALL, shims, b"{}", **kw)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _status_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.strip()]


# --- AC-26: output ------------------------------------------------------------


def test_advisory_passes_the_system_message_through_as_a_document(tmp_path, capsys):
    code, out, err = _run(capsys, tmp_path, _shim(tmp_path, EMIT_MESSAGE), advisory=True)
    assert code == 0
    assert json.loads(out) == {"systemMessage": MESSAGE}
    assert err == ""


def test_control_a_plain_stop_group_still_prints_plain_stdout(tmp_path, capsys):
    code, out, _ = _run(capsys, tmp_path, _shim(tmp_path, EMIT_MESSAGE))
    assert code == 0
    assert out.strip() == MESSAGE, "non-advisory Stop output is unchanged plain context"


def test_advisory_wraps_plain_text_and_joins_parts_in_one_document(tmp_path, capsys):
    shims = _shim(tmp_path, "print('first')\n", "Stop/a.py") + _shim(
        tmp_path, "print('second')\n", "Stop/b.py"
    )
    code, out, _ = _run(capsys, tmp_path, shims, advisory=True)
    assert code == 0
    assert json.loads(out) == {"systemMessage": "first\n\nsecond"}


def test_advisory_silent_shim_prints_nothing(tmp_path, capsys):
    code, out, err = _run(capsys, tmp_path, _shim(tmp_path, "pass\n"), advisory=True)
    assert (code, out, err) == (0, "", "")


def test_advisory_suppresses_a_block_decision_with_one_status_line(tmp_path, capsys):
    body = f"import json\nprint(json.dumps({BLOCK_DOC!r}))\n"
    code, out, err = _run(capsys, tmp_path, _shim(tmp_path, body), advisory=True)
    assert code == 0
    assert out == ""
    assert len(_status_lines(err)) == 1 and "advisory" in err


def test_control_a_plain_stop_group_still_emits_the_block_decision(tmp_path, capsys):
    body = f"import json\nprint(json.dumps({BLOCK_DOC!r}))\n"
    code, out, _ = _run(capsys, tmp_path, _shim(tmp_path, body))
    assert json.loads(out) == BLOCK_DOC
    assert code == 0


# --- AC-27: run_group failure paths -------------------------------------------

FAILING_BODIES = {
    "exits 3": "import sys\nsys.exit(3)\n",
    "exits 2": "import sys\nsys.exit(2)\n",
    "raises": "raise RuntimeError('boom')\n",
}


@pytest.mark.parametrize("body", FAILING_BODIES.values(), ids=FAILING_BODIES.keys())
def test_advisory_hook_failure_exits_zero_with_one_status_line(tmp_path, capsys, body):
    code, out, err = _run(capsys, tmp_path, _shim(tmp_path, body), advisory=True)
    assert code == 0
    assert out == ""
    assert len(_status_lines(err)) == 1, err


@pytest.mark.parametrize("body", FAILING_BODIES.values(), ids=FAILING_BODIES.keys())
def test_control_a_plain_stop_group_still_blocks_on_hook_failure(tmp_path, capsys, body):
    code, _, _ = _run(capsys, tmp_path, _shim(tmp_path, body))
    assert code != 0


def test_advisory_missing_shim_exits_zero_with_one_status_line(tmp_path, capsys):
    code, _, err = _run(capsys, tmp_path, ["Stop/absent.py"], advisory=True)
    assert code == 0
    assert len(_status_lines(err)) == 1


def test_control_a_plain_stop_group_still_blocks_on_a_missing_shim(tmp_path, capsys):
    code, _, _ = _run(capsys, tmp_path, ["Stop/absent.py"])
    assert code == chd.BLOCK_EXIT


def test_advisory_invalid_contract_exits_zero_with_one_status_line(tmp_path, capsys):
    code = chd.run_group(tmp_path, "Stop", chd.GATE_ALL, ["../escape.py"], b"{}", advisory=True)
    err = capsys.readouterr().err
    assert code == 0 and len(_status_lines(err)) == 1


def test_control_a_plain_group_still_blocks_on_an_invalid_contract(tmp_path, capsys):
    code = chd.run_group(tmp_path, "Stop", chd.GATE_ALL, ["../escape.py"], b"{}")
    assert code == chd.BLOCK_EXIT


@pytest.mark.parametrize("event", ["PreToolUse", "SessionStart", "UserPromptSubmit"])
def test_advisory_is_refused_off_stop_without_running_the_shim(tmp_path, capsys, event):
    marker = tmp_path / "ran"
    shims = _shim(tmp_path, f"open({str(marker)!r}, 'w').close()\n", "s.py")
    mode = chd.validate_group(event, chd._MODE_BY_EVENT[event], shims)[1]
    code = chd.run_group(tmp_path, event, mode, shims, b"{}", advisory=True)
    err = capsys.readouterr().err
    assert code == chd.BLOCK_EXIT
    assert not marker.exists()
    assert len(_status_lines(err)) == 1 and "Stop" in err


GATE_BLOCK_BODY = 'import sys\nprint(\'{"decision": "block", "reason": "x"}\')\nsys.exit(2)\n'


def test_advisory_never_passes_a_gate_mode_block_through(tmp_path, capsys):
    """Defense in depth: run_group refuses advisory off Stop, so call the inner runner."""
    shims = _shim(tmp_path, GATE_BLOCK_BODY)
    chd._run_group(tmp_path, "PreToolUse", chd.GATE, shims, b"{}", True)
    assert "block" not in capsys.readouterr().out


def test_control_a_plain_gate_group_still_passes_a_shim_block_through(tmp_path, capsys):
    shims = _shim(tmp_path, GATE_BLOCK_BODY)
    code = chd._run_group(tmp_path, "PreToolUse", chd.GATE, shims, b"{}", False)
    assert code == chd.BLOCK_EXIT and "block" in capsys.readouterr().out


# --- AC-27: launcher failure paths --------------------------------------------


def _group(monkeypatch, *, mode="gate_all", event="Stop", self_hosts=False):
    monkeypatch.setattr(entry, "_load_group", lambda _g: (event, mode, ["Stop/s.py"]))
    monkeypatch.setattr(entry, "_project_self_hosts_plugin", lambda: self_hosts)


def _stdin(monkeypatch, data: bytes) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))


RESERVED_GROUP = entry._ADVISORY_GROUP_ID


def _main_as(capsys, group: str, *flags: str):
    code = entry.main(["--group", group, *flags])
    return code, capsys.readouterr().err


def _main(capsys, *flags: str):
    return _main_as(capsys, RESERVED_GROUP, *flags)


def test_manifest_load_failure(monkeypatch, capsys):
    def fail(_g):
        raise RuntimeError("manifest loader failed")

    monkeypatch.setattr(entry, "_load_group", fail)
    code, err = _main_as(capsys, RESERVED_GROUP, "--advisory")
    assert code == 0 and len(_status_lines(err)) == 1 and "manifest loader failed" in err
    assert _main(capsys)[0] == 2, "control: no --advisory keeps the block exit"


def test_manifest_load_failure_fails_closed_for_any_other_group_id(monkeypatch, capsys):
    """The event is unknown here, so only the reserved Stop group may fail open."""

    def fail(_g):
        raise RuntimeError("manifest loader failed")

    monkeypatch.setattr(entry, "_load_group", fail)
    code, err = _main_as(capsys, "pretooluse-bash", "--advisory")
    assert code == 2 and len(_status_lines(err)) == 1


@pytest.mark.parametrize("event", ["PreToolUse", "UserPromptSubmit", "SessionStart"])
def test_advisory_on_a_non_stop_event_exits_two(monkeypatch, capsys, event):
    mode = chd._MODE_BY_EVENT[event]
    _group(monkeypatch, event=event, mode=mode)
    ran = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: ran.append(a) or 0)
    code, err = _main(capsys, "--advisory")
    assert code == 2 and len(_status_lines(err)) == 1 and "Stop" in err
    assert ran == [], "the refusal precedes any hook execution"


def test_advisory_on_a_non_stop_event_exits_two_even_when_the_project_self_hosts(
    monkeypatch, capsys
):
    _group(monkeypatch, event="PreToolUse", mode="gate", self_hosts=True)
    code, _ = _main(capsys, "--advisory")
    assert code == 2


def test_control_a_plain_non_stop_group_is_not_refused(monkeypatch, capsys):
    _group(monkeypatch, event="PreToolUse", mode="gate")
    _stdin(monkeypatch, b"{}")
    ran = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: ran.append(a) or 0)
    code, _ = _main(capsys)
    assert code == 0 and len(ran) == 1


def test_advisory_on_an_unreserved_stop_group_is_dropped_not_honored(monkeypatch, capsys):
    """ADR-071 reserves --advisory to one group. Exit 2 would block the Stop, so
    the launcher ignores the flag and the group keeps plain-group semantics."""
    _group(monkeypatch, event="Stop", mode="gate_all")
    _stdin(monkeypatch, b"{}")
    seen = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: seen.append(k["advisory"]) or 3)
    code, err = _main_as(capsys, "plugin-stop-2-other", "--advisory")
    assert seen == [False], "the flag is dropped before the group runs"
    assert code == 3, "plain-group semantics: the hook's own code is returned"
    assert "reserved" in err and len(_status_lines(err)) == 1


def test_control_the_reserved_stop_group_keeps_advisory(monkeypatch, capsys):
    _group(monkeypatch, event="Stop", mode="gate_all")
    _stdin(monkeypatch, b"{}")
    seen = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: seen.append(k["advisory"]) or 0)
    code, _ = _main_as(capsys, RESERVED_GROUP, "--advisory")
    assert seen == [True] and code == 0


def test_real_manifest_that_is_unreadable_fails_open(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(entry, "_HOOKS_DIR", tmp_path)  # no dispatch_groups.json here
    code, err = _main_as(capsys, RESERVED_GROUP, "--advisory")
    assert code == 0 and len(_status_lines(err)) == 1
    assert _main(capsys)[0] == 2


def test_oversized_stdin(monkeypatch, capsys):
    _group(monkeypatch)
    monkeypatch.setattr(entry, "_MAX_STDIN_BYTES", 8)
    _stdin(monkeypatch, b"x" * 64)
    code, err = _main(capsys, "--advisory")
    assert code == 0 and len(_status_lines(err)) == 1 and "exceeds" in err
    _stdin(monkeypatch, b"x" * 64)
    assert _main(capsys)[0] == 2, "control: a plain gate_all group denies"


def test_execution_exception(monkeypatch, capsys):
    _group(monkeypatch)
    _stdin(monkeypatch, b"{}")

    def explode(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(entry, "run_group", explode)
    code, err = _main(capsys, "--advisory")
    assert code == 0 and len(_status_lines(err)) == 1 and "disk gone" in err
    _stdin(monkeypatch, b"{}")
    assert _main(capsys)[0] == 2


def test_self_host_check_exception(monkeypatch, capsys):
    _group(monkeypatch)

    def fail():
        raise OSError("project directory unavailable")

    monkeypatch.setattr(entry, "_project_self_hosts_plugin", fail)
    code, err = _main(capsys, "--advisory")
    assert code == 0 and len(_status_lines(err)) == 1 and "self-host" in err
    code, err = _main(capsys)
    assert code == 2, "control: a plain gate_all group denies when the self-host check fails"


def test_nonzero_hook_exit_through_the_launcher(monkeypatch, tmp_path, capsys):
    _group(monkeypatch)
    _stdin(monkeypatch, b"{}")
    shims = _shim(tmp_path, "import sys\nsys.exit(3)\n")
    monkeypatch.setattr(entry, "_HOOKS_DIR", tmp_path)
    monkeypatch.setattr(entry, "_load_group", lambda _g: ("Stop", "gate_all", shims))
    code, err = _main(capsys, "--advisory")
    assert code == 0 and len(_status_lines(err)) == 1
    _stdin(monkeypatch, b"{}")
    assert _main(capsys)[0] == 3, "control: a plain group returns the hook's own code"


def test_launcher_passes_the_system_message_through(monkeypatch, tmp_path, capsys):
    _stdin(monkeypatch, b"{}")
    shims = _shim(tmp_path, EMIT_MESSAGE)
    monkeypatch.setattr(entry, "_HOOKS_DIR", tmp_path)
    monkeypatch.setattr(entry, "_load_group", lambda _g: ("Stop", "gate_all", shims))
    monkeypatch.setattr(entry, "_project_self_hosts_plugin", lambda: False)
    code = entry.main(["--group", RESERVED_GROUP, "--advisory"])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"systemMessage": MESSAGE}


# --- the self-host guard now covers an advisory gate_all group -----------------


def test_advisory_group_bails_inside_the_publishing_repo(monkeypatch, capsys):
    _group(monkeypatch, self_hosts=True)
    ran = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: ran.append(a) or 0)
    code, err = _main(capsys, "--advisory")
    assert (code, err, ran) == (0, "", [])


def test_control_a_plain_gate_all_group_still_skips_the_self_host_check(monkeypatch, capsys):
    _group(monkeypatch, self_hosts=True)
    _stdin(monkeypatch, b"{}")
    ran = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: ran.append(a) or 0)
    code, _ = _main(capsys)
    assert code == 0 and len(ran) == 1, "gate groups run even when the plugin self-hosts"


def test_failure_exit_helper():
    assert entry._failure_exit(True) == 0
    assert entry._failure_exit(False) == chd.BLOCK_EXIT
