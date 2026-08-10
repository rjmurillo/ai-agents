"""Tests for the Session Protocol Results prerequisite decision."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import check_session_aggregation_needed as session_gate

EXIT_CONFIG = session_gate.EXIT_CONFIG
EXIT_LOGIC = session_gate.EXIT_LOGIC
EXIT_OK = session_gate.EXIT_OK
decide = session_gate.decide
SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ci"
    / "check_session_aggregation_needed.py"
)


@pytest.mark.parametrize("detect_result", ["failure", "cancelled", ""])
def test_detect_failure_blocks(detect_result: str) -> None:
    exit_code, skip, expected, artifacts, _message = decide(
        "success", "true", detect_result, "", "skipped", ""
    )
    assert exit_code == EXIT_LOGIC
    assert skip is False
    assert expected == 0
    assert artifacts == "{}"


def test_check_changes_failure_blocks() -> None:
    exit_code, skip, expected, artifacts, _message = decide(
        "failure", "false", "skipped", "", "skipped", ""
    )
    assert exit_code == EXIT_LOGIC
    assert skip is False
    assert expected == 0
    assert artifacts == "{}"


def test_no_session_changes_skips() -> None:
    assert decide("success", "true", "success", "false", "skipped", "[]") == (
        EXIT_OK,
        True,
        0,
        "{}",
        "Skipped - no session file changes detected",
    )


def test_skipped_detection_skips() -> None:
    assert decide("success", "false", "skipped", "", "skipped", "") == (
        EXIT_OK,
        True,
        0,
        "{}",
        "Skipped - no session file changes detected",
    )


def test_success_without_decision_blocks() -> None:
    exit_code, skip, expected, artifacts, _message = decide(
        "success", "true", "success", "", "skipped", ""
    )
    assert exit_code == EXIT_LOGIC
    assert skip is False
    assert expected == 0
    assert artifacts == "{}"


def test_missing_filter_decision_blocks() -> None:
    exit_code, skip, expected, artifacts, _message = decide(
        "success", "", "skipped", "", "skipped", ""
    )
    assert exit_code == EXIT_LOGIC
    assert skip is False
    assert expected == 0
    assert artifacts == "{}"


def test_skipped_detection_blocks_when_filter_requires_validation() -> None:
    exit_code, skip, expected, artifacts, _message = decide(
        "success", "true", "skipped", "", "skipped", ""
    )
    assert exit_code == EXIT_LOGIC
    assert skip is False
    assert expected == 0
    assert artifacts == "{}"


def test_sessions_require_aggregation() -> None:
    assert decide(
        "success",
        "true",
        "success",
        "true",
        "success",
        '[".agents/sessions/session-1.json", ".agents/sessions/session-2.json"]',
    ) == (
        EXIT_OK,
        False,
        2,
        '{"sessions-session-1":".agents/sessions/session-1.json",'
        '"sessions-session-2":".agents/sessions/session-2.json"}',
        "Session validation artifacts require aggregation",
    )


@pytest.mark.parametrize(
    ("validate_result", "session_files"),
    [("failure", '["session-1.json"]'), ("success", "not-json"), ("success", "[]")],
)
def test_validation_or_matrix_failure_blocks(
    validate_result: str,
    session_files: str,
) -> None:
    exit_code, skip, expected, artifacts, _message = decide(
        "success",
        "true",
        "success",
        "true",
        validate_result,
        session_files,
    )
    assert exit_code == EXIT_LOGIC
    assert skip is False
    assert expected == 0
    assert artifacts == "{}"


def test_main_writes_skip_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    env = {
        "GITHUB_OUTPUT": str(output),
        "CHECK_CHANGES_RESULT": "success",
        "SHOULD_RUN_PROTOCOL": "false",
        "DETECT_CHANGES_RESULT": "skipped",
        "HAS_SESSIONS": "",
        "VALIDATE_RESULT": "skipped",
        "SESSION_FILES": "",
    }
    with patch.dict(os.environ, env, clear=True):
        assert session_gate.main() == EXIT_OK
    assert output.read_text(encoding="utf-8") == (
        "skip=true\nexpected_results=0\nexpected_artifacts={}\n"
    )


def test_main_requires_github_output() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert session_gate.main() == EXIT_CONFIG


def test_script_runs_from_foreign_cwd(tmp_path: Path) -> None:
    output = tmp_path / "output"
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(output),
        "CHECK_CHANGES_RESULT": "success",
        "SHOULD_RUN_PROTOCOL": "false",
        "DETECT_CHANGES_RESULT": "skipped",
        "HAS_SESSIONS": "",
        "VALIDATE_RESULT": "skipped",
        "SESSION_FILES": "",
    }

    completed = subprocess.run(
        [sys.executable, "-I", str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == EXIT_OK
    assert "ModuleNotFoundError" not in completed.stderr
