#!/usr/bin/env python3
"""Prompt-preserving groups in the Claude hook launcher (issue #7493, ADR-109 amendment 2026-11-20).

Exit 2 on ``UserPromptSubmit`` blocks the prompt and erases it. The memory
recall group enforces no policy, so every launcher failure path for its
reserved id exits 0 after one stderr line. Each test has a control that runs
the same failure for an unreserved gate group and asserts exit 2.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for search_path in (str(REPO_ROOT / ".claude" / "lib"), str(REPO_ROOT / ".claude" / "hooks")):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

import invoke_dispatch_claude as entry

RECALL = "plugin-userpromptsubmit-1-memory_recall"
OTHER = "userpromptsubmit-1-other"
SHIM = "UserPromptSubmit/s.py"


def _group(monkeypatch: pytest.MonkeyPatch, *, self_hosts: bool = False) -> None:
    monkeypatch.setattr(entry, "_load_group", lambda _g: ("UserPromptSubmit", "gate_all", [SHIM]))
    monkeypatch.setattr(entry, "_project_self_hosts_plugin", lambda: self_hosts)


def _stdin(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))


def _status_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.strip()]


def test_the_reserved_set_names_exactly_the_recall_group() -> None:
    assert entry._PROMPT_PRESERVING_GROUP_IDS == frozenset({RECALL})


def test_the_reserved_id_is_a_group_in_the_manifest() -> None:
    import json

    manifest = json.loads((REPO_ROOT / ".claude" / "hooks" / "dispatch_groups.json").read_text())

    assert manifest["groups"][RECALL]["event"] == "UserPromptSubmit"


@pytest.mark.parametrize(("group", "expected"), [(RECALL, 0), (OTHER, 2)])
def test_manifest_load_failure(monkeypatch, capsys, group, expected) -> None:
    def fail(_group_id: str):
        raise ValueError("corrupt manifest")

    monkeypatch.setattr(entry, "_load_group", fail)

    code = entry.main(["--group", group])

    assert code == expected
    assert len(_status_lines(capsys.readouterr().err)) == 1


@pytest.mark.parametrize(("group", "expected"), [(RECALL, 0), (OTHER, 2)])
def test_self_host_check_exception(monkeypatch, capsys, group, expected) -> None:
    _group(monkeypatch)

    def explode() -> bool:
        raise OSError("boom")

    monkeypatch.setattr(entry, "_project_self_hosts_plugin", explode)
    ran: list[object] = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: ran.append(a) or 0)

    code = entry.main(["--group", group])

    assert code == expected
    assert len(_status_lines(capsys.readouterr().err)) == 1
    assert ran == []


def test_the_recall_group_gets_the_self_host_check(monkeypatch, capsys) -> None:
    """Inside the publishing checkout the project registration already runs recall."""
    _group(monkeypatch, self_hosts=True)
    ran: list[object] = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: ran.append(a) or 0)

    code = entry.main(["--group", RECALL])

    assert code == 0
    assert ran == []


def test_control_an_unreserved_gate_group_skips_the_self_host_check(monkeypatch, capsys) -> None:
    _group(monkeypatch, self_hosts=True)
    _stdin(monkeypatch, b"{}")
    ran: list[object] = []
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: ran.append(a) or 0)

    code = entry.main(["--group", OTHER])

    assert code == 0
    assert len(ran) == 1


@pytest.mark.parametrize(("group", "expected"), [(RECALL, 0), (OTHER, 2)])
def test_oversized_stdin(monkeypatch, capsys, group, expected) -> None:
    _group(monkeypatch)
    monkeypatch.setattr(entry, "_MAX_STDIN_BYTES", 8)
    _stdin(monkeypatch, b"x" * 64)

    code = entry.main(["--group", group])

    assert code == expected
    assert len(_status_lines(capsys.readouterr().err)) == 1


@pytest.mark.parametrize(("group", "expected"), [(RECALL, 0), (OTHER, 2)])
def test_execution_exception(monkeypatch, capsys, group, expected) -> None:
    _group(monkeypatch)
    _stdin(monkeypatch, b"{}")

    def explode(*_a, **_k):
        raise RuntimeError("shim crashed")

    monkeypatch.setattr(entry, "run_group", explode)

    code = entry.main(["--group", group])

    assert code == expected
    assert len(_status_lines(capsys.readouterr().err)) == 1


@pytest.mark.parametrize(("group", "expected"), [(RECALL, 0), (OTHER, 3)])
def test_non_zero_run_group_result(monkeypatch, capsys, group, expected) -> None:
    _group(monkeypatch)
    _stdin(monkeypatch, b"{}")
    monkeypatch.setattr(entry, "run_group", lambda *a, **k: 3)

    code = entry.main(["--group", group])

    assert code == expected
    err_lines = _status_lines(capsys.readouterr().err)
    assert len(err_lines) == (1 if group == RECALL else 0)


def test_the_advisory_flag_on_the_recall_group_still_exits_zero(monkeypatch, capsys) -> None:
    _group(monkeypatch)

    code = entry.main(["--group", RECALL, "--advisory"])

    assert code == 0
    assert len(_status_lines(capsys.readouterr().err)) == 1


# --- a shim's blocking decision never reaches the host (real run_group) --------

# `decision: block` is the shape the brief names. For UserPromptSubmit the
# protocol module treats it as unsupported (a gate failure). `continue: false`
# is the shape it accepts as a real block, so both are exercised.
DECISION_BLOCK = {"decision": "block", "reason": "x"}
CONTINUE_FALSE = {"continue": False, "stopReason": "x"}


def _block_shim(document: dict[str, object]) -> str:
    return (
        "import json\n"
        "from pathlib import Path\n"
        "Path(__file__).with_name('ran.marker').write_text('ran')\n"
        f"print(json.dumps({document!r}))\n"
    )


def _plant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    group: str,
    event: str = "UserPromptSubmit",
    document: dict[str, object] | None = None,
) -> Path:
    """A real hooks dir whose manifest holds ``group`` with a shim that emits a block."""
    import json

    shim = tmp_path / SHIM
    shim.parent.mkdir(parents=True)
    shim.write_text(_block_shim(document or DECISION_BLOCK), encoding="utf-8")
    manifest = {
        "groups": {
            group: {"event": event, "mode": "gate_all", "matcher": None, "shims": [{"file": SHIM}]}
        }
    }
    (tmp_path / "dispatch_groups.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(entry, "_HOOKS_DIR", tmp_path)
    monkeypatch.setattr(entry, "_project_self_hosts_plugin", lambda: False)
    _stdin(monkeypatch, b"{}")
    return shim.with_name("ran.marker")


@pytest.mark.parametrize("document", [DECISION_BLOCK, CONTINUE_FALSE])
def test_a_blocking_document_from_the_recall_group_never_reaches_the_host(
    monkeypatch, capsys, tmp_path, document
) -> None:
    marker = _plant(monkeypatch, tmp_path, RECALL, document=document)

    code = entry.main(["--group", RECALL])

    captured = capsys.readouterr()
    assert marker.exists(), "the shim must have run, or this proves nothing"
    assert code == 0
    assert captured.out == ""
    assert _status_lines(captured.err)


def test_a_valid_block_is_suppressed_by_the_prompt_preserving_policy(
    monkeypatch, capsys, tmp_path
) -> None:
    _plant(monkeypatch, tmp_path, RECALL, document=CONTINUE_FALSE)

    entry.main(["--group", RECALL])

    assert "suppressing decision in prompt-preserving mode" in capsys.readouterr().err


def test_control_an_unreserved_group_still_forwards_a_valid_block(
    monkeypatch, capsys, tmp_path
) -> None:
    marker = _plant(monkeypatch, tmp_path, OTHER, document=CONTINUE_FALSE)

    code = entry.main(["--group", OTHER])

    captured = capsys.readouterr()
    assert marker.exists()
    assert code == 0
    assert '"continue": false' in captured.out


def test_control_an_unreserved_group_exits_two_on_the_unsupported_shape(
    monkeypatch, capsys, tmp_path
) -> None:
    _plant(monkeypatch, tmp_path, OTHER, document=DECISION_BLOCK)

    assert entry.main(["--group", OTHER]) == 2


def test_a_reserved_id_registered_for_another_event_is_not_run(
    monkeypatch, capsys, tmp_path
) -> None:
    marker = _plant(monkeypatch, tmp_path, RECALL, event="Stop")

    code = entry.main(["--group", RECALL])

    err_lines = _status_lines(capsys.readouterr().err)
    assert code == 0
    assert not marker.exists()
    assert len(err_lines) == 1
    assert "UserPromptSubmit" in err_lines[0]


def test_control_an_unreserved_id_on_another_event_still_runs(
    monkeypatch, capsys, tmp_path
) -> None:
    marker = _plant(monkeypatch, tmp_path, OTHER, event="Stop")

    entry.main(["--group", OTHER])

    assert marker.exists()
