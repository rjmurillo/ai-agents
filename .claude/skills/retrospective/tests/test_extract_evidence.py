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
from datetime import date
from hashlib import sha1
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SCRIPT = _SCRIPT_DIR / "extract_evidence.py"
_MODULE_NAME = f"retrospective_extract_evidence_{sha1(str(_SCRIPT).encode()).hexdigest()[:12]}"
_GIT_TEST_TIMEOUT_SECONDS = 30

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod
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
        subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            check=True,
            timeout=_GIT_TEST_TIMEOUT_SECONDS,
        )
    (root / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(
        ["git", "add", "."],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=_GIT_TEST_TIMEOUT_SECONDS,
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: seed commit for evidence test"],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=_GIT_TEST_TIMEOUT_SECONDS,
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
    chosen = find_recent_session_log(sessions, today=date(2026, 6, 10))

    # Assert
    assert chosen == new


def test_find_recent_session_log_prefers_today_over_newer_older_log(tmp_path):
    # Arrange: an older-day log has newer mtime, but today's log wins.
    sessions = tmp_path / ".agents" / "sessions"
    older = _write_session(
        sessions, "2026-05-31-session-9-old.json", {"workLog": ["old work"]}
    )
    today = _write_session(
        sessions, "2026-06-03-session-1-today.json", {"workLog": ["today work"]}
    )
    import os

    os.utime(today, (1_000_000, 1_000_000))
    os.utime(older, (2_000_000, 2_000_000))

    # Act
    chosen = find_recent_session_log(sessions, today=date(2026, 6, 3))

    # Assert
    assert chosen == today


def test_find_recent_session_log_uses_yesterday_when_today_missing(tmp_path):
    # Arrange
    sessions = tmp_path / ".agents" / "sessions"
    older = _write_session(
        sessions, "2026-05-31-session-9-old.json", {"workLog": ["old work"]}
    )
    yesterday = _write_session(
        sessions, "2026-06-02-session-1-yesterday.json", {"workLog": ["yesterday"]}
    )
    import os

    os.utime(yesterday, (1_000_000, 1_000_000))
    os.utime(older, (2_000_000, 2_000_000))

    # Act
    chosen = find_recent_session_log(sessions, today=date(2026, 6, 3))

    # Assert
    assert chosen == yesterday


def test_gather_evidence_uses_scope_date_for_session_selection(tmp_path):
    # Arrange: current-day work exists, but the retrospective is scoped earlier.
    sessions = tmp_path / ".agents" / "sessions"
    _write_session(sessions, "2026-06-04-session-1-current.json", {"workLog": ["current"]})
    scoped = _write_session(
        sessions, "2026-06-03-session-1-scoped.json", {"workLog": ["scoped"]}
    )

    # Act
    evidence = gather_evidence(tmp_path, "2026-06-03")

    # Assert
    assert evidence.session_log_path == str(scoped)
    assert evidence.work_items == ["scoped"]


def test_gather_evidence_defaults_git_since_from_scope_date(tmp_path, monkeypatch):
    # Arrange
    sessions = tmp_path / ".agents" / "sessions"
    _write_session(sessions, "2026-06-03-session-1-scoped.json", {"workLog": ["scoped"]})
    seen: dict[str, str | None] = {}

    def _fake_git_log(_project_dir, since):
        seen["since"] = since
        return True, []

    monkeypatch.setattr(_mod, "gather_git_log", _fake_git_log)

    # Act
    gather_evidence(tmp_path, "2026-06-03")

    # Assert
    assert seen["since"] == "2026-06-03"


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
    result = parse_session_log(path)
    work, outcomes = result

    # Assert: degraded to empty, no exception.
    assert work == []
    assert outcomes == []
    assert result.error is not None


def test_parse_session_log_returns_error_on_invalid_utf8(tmp_path):
    # Arrange: invalid UTF-8 on disk.
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True)
    path = sessions / "2026-06-03-session-0-bad-utf8.json"
    path.write_bytes(b"\xff")

    # Act
    result = parse_session_log(path)

    # Assert: degraded to empty, no exception.
    assert result.work_items == []
    assert result.outcomes == []
    assert "UnicodeDecodeError" in result.error


def test_parse_session_log_respects_explicit_empty_worklog(tmp_path):
    # Arrange: the current field is authoritative even when empty.
    sessions = tmp_path / ".agents" / "sessions"
    path = _write_session(
        sessions,
        "2026-06-03-session-4-empty-current.json",
        {"workLog": [], "work": ["legacy work"]},
    )

    # Act
    result = parse_session_log(path)

    # Assert
    assert result.work_items == []
    assert result.error is None


def test_gather_evidence_marks_parse_failure_not_empty_session(tmp_path):
    # Arrange: a corrupt log should not be described as an empty session.
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True)
    path = sessions / "2026-06-03-session-0-bad.json"
    path.write_text("{not json", encoding="utf-8")

    # Act
    evidence = gather_evidence(tmp_path, "bad")

    # Assert
    assert evidence.session_log_path == str(path)
    assert evidence.session_log_available is False
    assert any("could not be parsed" in note for note in evidence.notes)
    assert not any("no work or outcomes" in note for note in evidence.notes)


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
