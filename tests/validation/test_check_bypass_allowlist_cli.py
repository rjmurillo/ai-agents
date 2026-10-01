"""The bypass gate CLI: exit codes, stale entries, and unreadable input.

Issue #5636, decision D17. The whole-tree test at the end runs with today's date on
purpose: an expired entry must fail the suite.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import check_bypass_allowlist as gate
from scripts.validation.bypass_allowlist import ALLOWLIST_RELATIVE_PATH
from scripts.validation.evidence import EvidenceState
from tests.validation.bypass_gate_helpers import (
    TODAY,
    WORKFLOW,
    allow,
    make_repo,
    run_gate,
    step,
    toggle,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- stale, unreadable, and configuration ----------------------------------


def test_a_stale_entry_is_reported_and_does_not_fail(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.py": "x = 1\n"})

    outcome, stale = gate.evaluate(root, allow(toggle("SKIP_GONE"), step("j", "s")), TODAY)

    assert outcome.state is EvidenceState.PASS
    assert len(stale) == 2
    assert any("SKIP_GONE" in item for item in stale)


def test_a_python_file_that_does_not_parse_blocks_the_scan(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.py": "def broken(:\n"})

    outcome, _ = gate.evaluate(root, allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == "entries.unreadable"
    assert "a.py does not parse" in outcome.detail


def test_a_workflow_that_is_not_yaml_blocks_the_scan(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {WORKFLOW: "jobs: [unclosed\n"})

    outcome, _ = gate.evaluate(root, allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert "is not YAML" in outcome.detail


def test_a_tracked_file_deleted_from_the_working_tree_is_skipped(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})
    (root / "a.sh").unlink()

    state, detail = run_gate(root, allow())

    assert state is EvidenceState.PASS, detail


def test_a_tracked_file_that_cannot_be_read_blocks_the_scan(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.sh": "x\n"})
    (root / "a.sh").unlink()
    (root / "a.sh").mkdir()

    outcome, _ = gate.evaluate(root, allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert "a.sh unreadable" in outcome.detail


def test_a_directory_that_is_not_a_repository_blocks_the_scan(tmp_path: Path) -> None:
    outcome, _ = gate.evaluate(tmp_path, allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == "listing.failed"


def test_a_missing_git_binary_blocks_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(gate.subprocess, "run", boom)

    outcome, _ = gate.evaluate(tmp_path, allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED
    assert "could not run" in outcome.detail


def test_a_git_timeout_blocks_the_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(gate.subprocess, "run", boom)

    outcome, _ = gate.evaluate(tmp_path, allow(), TODAY)

    assert outcome.state is EvidenceState.BLOCKED


# --- the CLI: the process exit code is the contract ------------------------


def _write_allowlist(root: Path, *entries: dict[str, Any]) -> None:
    target = root / ALLOWLIST_RELATIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": "1", "entries": list(entries)}
    target.write_text(json.dumps(document), encoding="utf-8")


def test_main_exits_zero_when_every_use_is_authorized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})
    _write_allowlist(root, toggle("SKIP_THING"))

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    assert rc == 0
    assert capsys.readouterr().out.startswith("[PASS] validate_bypass_allowlist")


def test_main_exits_one_on_an_unlisted_use(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    assert rc == 1
    out = capsys.readouterr().out
    assert out.startswith("[FAIL] validate_bypass_allowlist reason=violations.found")
    assert "findings=1" in out


def test_main_exits_one_on_an_expired_entry(tmp_path: Path) -> None:
    root = make_repo(tmp_path, {"a.sh": "export SKIP_THING=0\n"})
    _write_allowlist(root, toggle("SKIP_THING", expires="2026-09-29"))

    assert gate.main(["--repo-root", str(root), "--today", "2026-09-30"]) == 1


def test_main_exits_two_on_an_invalid_allowlist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path, {"a.sh": "x\n"})
    _write_allowlist(root, {"kind": "toggle", "toggle": "nope"})

    rc = gate.main(["--repo-root", str(root)])

    assert rc == 2
    assert "bypass allowlist is invalid" in capsys.readouterr().err


def test_main_exits_three_when_the_tree_cannot_be_read(tmp_path: Path) -> None:
    assert gate.main(["--repo-root", str(tmp_path)]) == 3


def test_main_prints_a_stale_notice_and_still_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path, {"a.py": "x = 1\n"})
    _write_allowlist(root, toggle("SKIP_GONE"))

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    assert rc == 0
    assert "[NOTICE] stale allowlist entry" in capsys.readouterr().out


def test_main_keeps_a_newline_in_a_path_from_forging_a_second_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hostile = 'evil"\n::error::forged.sh'
    root = make_repo(tmp_path, {hostile: "export SKIP_THING=0\n"})

    rc = gate.main(["--repo-root", str(root), "--today", "2026-09-30"])

    lines = capsys.readouterr().out.splitlines()
    assert rc == 1
    assert len(lines) == 1
    assert not any(line.startswith("::error::") for line in lines)


# --- this repository -------------------------------------------------------


def test_every_bypass_in_this_repository_is_authorized_and_unexpired() -> None:
    """Runs with the real date on purpose: an expired entry must fail the suite."""
    outcome = gate.validate_bypass_allowlist(REPO_ROOT)

    assert outcome.state is EvidenceState.PASS, outcome.report_line()


def test_a_text_mode_subprocess_double_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-PR runner's tests replace subprocess.run with a str-returning double."""

    def double(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout="a.txt\0b.txt\0", stderr=""
        )

    monkeypatch.setattr(gate.subprocess, "run", double)

    assert gate.tracked_files(tmp_path) == ["a.txt", "b.txt"]
