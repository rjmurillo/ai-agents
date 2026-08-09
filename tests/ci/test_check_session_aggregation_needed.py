"""Tests for the Session Protocol Results prerequisite decision."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci.check_session_aggregation_needed import (
    EXIT_CONFIG,
    EXIT_LOGIC,
    EXIT_OK,
    decide,
    main,
)


@pytest.mark.parametrize("detect_result", ["failure", "cancelled", ""])
def test_detect_failure_blocks(detect_result: str) -> None:
    exit_code, skip, _message = decide("success", detect_result, "")
    assert exit_code == EXIT_LOGIC
    assert skip is False


def test_check_changes_failure_blocks() -> None:
    exit_code, skip, _message = decide("failure", "skipped", "")
    assert exit_code == EXIT_LOGIC
    assert skip is False


def test_no_session_changes_skips() -> None:
    assert decide("success", "success", "false") == (
        EXIT_OK,
        True,
        "Skipped - no session file changes detected",
    )


def test_skipped_detection_skips() -> None:
    assert decide("success", "skipped", "") == (
        EXIT_OK,
        True,
        "Skipped - no session file changes detected",
    )


def test_success_without_decision_blocks() -> None:
    exit_code, skip, _message = decide("success", "success", "")
    assert exit_code == EXIT_LOGIC
    assert skip is False


def test_sessions_require_aggregation() -> None:
    assert decide("success", "success", "true") == (
        EXIT_OK,
        False,
        "Session validation artifacts require aggregation",
    )


def test_main_writes_skip_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    env = {
        "GITHUB_OUTPUT": str(output),
        "CHECK_CHANGES_RESULT": "success",
        "DETECT_CHANGES_RESULT": "skipped",
        "HAS_SESSIONS": "",
    }
    with patch.dict(os.environ, env, clear=True):
        assert main() == EXIT_OK
    assert output.read_text(encoding="utf-8") == "skip=true\n"


def test_main_requires_github_output() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert main() == EXIT_CONFIG
