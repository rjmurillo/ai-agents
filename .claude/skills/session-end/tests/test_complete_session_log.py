#!/usr/bin/env python3
"""Tests for session-end skill complete_session_log.py."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
from unittest import mock

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "complete_session_log.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("complete_session_log", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCompleteSessionLog:
    def _make_session_json(self, sessions_dir, name="2026-02-11-session-1.json"):
        """Create a minimal valid session JSON for testing."""
        session = {
            "session": {
                "number": 1,
                "date": "2026-02-11",
                "branch": "feat/test",
                "startingCommit": "abc1234",
                "objective": "Test session",
            },
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"level": "MUST", "Complete": True, "Evidence": "done"},
                },
                "sessionEnd": {
                    "checklistComplete": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "handoffNotUpdated": {"level": "MUST NOT", "Complete": False, "Evidence": ""},
                    "serenaMemoryUpdated": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "markdownLintRun": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "changesCommitted": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "validationPassed": {"level": "MUST", "Complete": False, "Evidence": ""},
                    "tasksUpdated": {"level": "SHOULD", "Complete": False, "Evidence": ""},
                    "retrospectiveInvoked": {"level": "SHOULD", "Complete": False, "Evidence": ""},
                },
            },
            "workLog": [],
            "endingCommit": "",
            "nextSteps": [],
        }
        path = os.path.join(sessions_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        return path

    def test_dry_run_no_changes(self, tmp_path):
        sessions_dir = str(tmp_path / ".agents" / "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        session_path = self._make_session_json(sessions_dir)

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1:3] == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=str(tmp_path), stderr="")
            if cmd[0] == "git" and cmd[1:4] == ["rev-parse", "--short", "HEAD"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="abc1234", stderr="")
            if cmd[0] == "git":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[0] == "npx":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")

        mod = _load_module()
        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--session-path", session_path, "--dry-run"])

        # Dry run should succeed (0) or report todos (1) depending on evidence state
        assert result in (0, 1)

        # Verify file was NOT modified (dry run)
        with open(session_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["endingCommit"] == ""

    def test_missing_session_file_returns_1(self, tmp_path):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1:3] == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=str(tmp_path), stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--session-path", "/nonexistent/file.json"])

        assert result == 1

    def test_invalid_json_returns_1(self, tmp_path):
        sessions_dir = str(tmp_path / ".agents" / "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        bad_file = os.path.join(sessions_dir, "bad.json")
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("not json")

        mod = _load_module()

        def mock_run(cmd, **kwargs):
            if cmd[0] == "git" and cmd[1:3] == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=str(tmp_path), stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--session-path", bad_file])

        assert result == 1
