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
