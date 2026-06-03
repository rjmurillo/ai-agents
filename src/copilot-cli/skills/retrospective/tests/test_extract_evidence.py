"""Tests for extract_evidence.py.

Covers a populated session log (positive), missing sources marked absent
(negative), schema-shape edge cases, the bounded git call, and the CLI argv
boundary. I/O is exercised against tmp_path; git is exercised against a real
throwaway repo to avoid mocking the function under test.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SCRIPT = _SCRIPT_DIR / "extract_evidence.py"

_spec = importlib.util.spec_from_file_location("extract_evidence", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["extract_evidence"] = _mod
_spec.loader.exec_module(_mod)

gather_evidence = _mod.gather_evidence
find_recent_session_log = _mod.find_recent_session_log
parse_session_log = _mod.parse_session_log
gather_git_log = _mod.gather_git_log
main = _mod.main


def _write_session(sessions_dir: Path, name: str, payload: dict) -> Path:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _init_git_repo(root: Path) -> None:
    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ):
        subprocess.run(cmd, cwd=root, capture_output=True, check=True)
    (root / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: seed commit for evidence test"],
        cwd=root,
        capture_output=True,
        check=True,
    )


# --- Positive: a populated session log yields work items --------------------


def test_gather_evidence_reads_worklog_session(tmp_path):
    # Arrange: a session with the current workLog schema.
    sessions = tmp_path / ".agents" / "sessions"
    _write_session(
        sessions,
        "2026-06-03-session-1-demo.json",
        {"workLog": [{"step": 1, "action": "Fixed the parser", "outcome": "green"}]},
    )

    # Act
    evidence = gather_evidence(tmp_path, "demo")

    # Assert
    assert evidence.session_log_available is True
    assert evidence.work_items == ["Step 1: Fixed the parser -> green"]
    assert evidence.scope == "demo"


def test_gather_evidence_picks_most_recent_session(tmp_path):
    # Arrange: two sessions; the newer one wins by mtime.
    sessions = tmp_path / ".agents" / "sessions"
    old = _write_session(
        sessions, "2026-06-01-session-1-old.json", {"workLog": ["old work"]}
    )
    new = _write_session(
        sessions, "2026-06-03-session-2-new.json", {"workLog": ["new work"]}
    )
    # Force ordering: make `new` newer than `old`.
    import os

    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))

    # Act
    chosen = find_recent_session_log(sessions)

    # Assert
    assert chosen == new


# --- Negative: missing sources are marked absent, not crashed ---------------


def test_gather_evidence_marks_session_absent_when_none(tmp_path):
    # Arrange: directory exists but holds no session logs, no git repo.
    (tmp_path / ".agents" / "sessions").mkdir(parents=True)

    # Act
    evidence = gather_evidence(tmp_path, "empty")

    # Assert: degraded, with notes, not an exception.
    assert evidence.session_log_available is False
    assert evidence.work_items == []
    assert evidence.git_available is False
    assert any("session log" in note.lower() for note in evidence.notes)
    assert any("git" in note.lower() for note in evidence.notes)


def test_find_recent_session_log_returns_none_for_missing_dir(tmp_path):
    # Arrange: the sessions directory does not exist.
    missing = tmp_path / "nope" / "sessions"

    # Act / Assert
    assert find_recent_session_log(missing) is None


# --- Edge: schema variety and corrupt input --------------------------------


def test_parse_session_log_handles_legacy_work_shape(tmp_path):
    # Arrange: legacy flat ``work`` list with description entries.
    sessions = tmp_path / ".agents" / "sessions"
    path = _write_session(
        sessions,
        "2026-06-03-session-9-legacy.json",
        {"work": [{"description": "Wrote the adapter"}], "outcomes": ["shipped"]},
    )

    # Act
    work, outcomes = parse_session_log(path)

    # Assert
    assert work == ["Wrote the adapter"]
    assert outcomes == ["shipped"]


def test_parse_session_log_returns_empty_on_corrupt_json(tmp_path):
    # Arrange: invalid JSON on disk.
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True)
    path = sessions / "2026-06-03-session-0-bad.json"
    path.write_text("{not json", encoding="utf-8")

    # Act
    work, outcomes = parse_session_log(path)

    # Assert: degraded to empty, no exception.
    assert work == []
    assert outcomes == []


def test_session_with_no_work_is_marked_unavailable(tmp_path):
    # Arrange: a valid session log with empty work and outcomes.
    sessions = tmp_path / ".agents" / "sessions"
    _write_session(sessions, "2026-06-03-session-3-blank.json", {"workLog": []})

    # Act
    evidence = gather_evidence(tmp_path, "blank")

    # Assert: parseable but empty counts as degraded.
    assert evidence.session_log_available is False
    assert any("no work" in note.lower() for note in evidence.notes)


# --- git boundary -----------------------------------------------------------


def test_gather_git_log_reads_real_repo(tmp_path):
    # Arrange: a throwaway git repo with one commit.
    _init_git_repo(tmp_path)

    # Act
    available, commits = gather_git_log(tmp_path, since=None)

    # Assert
    assert available is True
    assert any("seed commit" in c for c in commits)


def test_gather_git_log_marks_unavailable_outside_repo(tmp_path):
    # Arrange: not a git repo.

    # Act
    available, commits = gather_git_log(tmp_path, since=None)

    # Assert
    assert available is False
    assert commits == []


# --- CLI argv boundary ------------------------------------------------------


def test_cli_emits_json_and_exits_zero(tmp_path, capsys):
    # Arrange
    sessions = tmp_path / ".agents" / "sessions"
    _write_session(sessions, "2026-06-03-session-1-cli.json", {"workLog": ["did a thing"]})

    # Act
    rc = main(["--scope", "cli", "--project-dir", str(tmp_path)])
    out = capsys.readouterr().out

    # Assert
    assert rc == 0
    payload = json.loads(out)
    assert payload["scope"] == "cli"
    assert payload["work_items"] == ["did a thing"]


def test_cli_returns_two_for_bad_project_dir(tmp_path):
    # Arrange: a path that is not a directory.
    not_a_dir = tmp_path / "missing"

    # Act
    rc = main(["--project-dir", str(not_a_dir)])

    # Assert
    assert rc == 2


def test_cli_subprocess_exit_code_zero(tmp_path):
    # Arrange
    sessions = tmp_path / ".agents" / "sessions"
    _write_session(sessions, "2026-06-03-session-1-sub.json", {"workLog": ["sub work"]})

    # Act
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-dir", str(tmp_path), "--scope", "sub"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Assert
    assert result.returncode == 0
    assert json.loads(result.stdout)["scope"] == "sub"
