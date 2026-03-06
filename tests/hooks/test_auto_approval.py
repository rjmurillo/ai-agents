#!/usr/bin/env python3
"""Tests for the test auto-approval hook.

Covers: safe test commands, dangerous metacharacters, missing command,
tty input, empty input, invalid JSON, all test framework patterns.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HOOK_DIR = str(
    Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PermissionRequest"
)
sys.path.insert(0, HOOK_DIR)

import invoke_test_auto_approval  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests for get_command_from_input
# ---------------------------------------------------------------------------


class TestGetCommandFromInput:
    """Tests for get_command_from_input function."""

    def test_extracts_command(self):
        hook_input = {"tool_input": {"command": "npm test"}}
        assert invoke_test_auto_approval.get_command_from_input(hook_input) == "npm test"

    def test_returns_none_when_no_tool_input(self):
        assert invoke_test_auto_approval.get_command_from_input({}) is None

    def test_returns_none_when_tool_input_not_dict(self):
        assert invoke_test_auto_approval.get_command_from_input(
            {"tool_input": "string"}
        ) is None

    def test_returns_none_when_no_command(self):
        assert invoke_test_auto_approval.get_command_from_input(
            {"tool_input": {"other": "value"}}
        ) is None

    def test_returns_none_when_command_not_string(self):
        assert invoke_test_auto_approval.get_command_from_input(
            {"tool_input": {"command": 123}}
        ) is None


# ---------------------------------------------------------------------------
# Unit tests for is_safe_test_command
# ---------------------------------------------------------------------------


class TestIsSafeTestCommand:
    """Tests for is_safe_test_command function."""

    @pytest.mark.parametrize(
        "command",
        [
            "pytest",
            "pytest tests/",
            "pytest -v --tb=short",
            "python -m pytest",
            "python -m pytest tests/",
            "npm test",
            "npm run test",
            "pnpm test",
            "yarn test",
            "dotnet test",
            "mvn test",
            "gradle test",
            "cargo test",
            "go test",
            "go test ./...",
            "pwsh -NoProfile Invoke-Pester",
            "pwsh -File Invoke-Pester -Path tests/",
        ],
    )
    def test_approves_safe_commands(self, command):
        assert invoke_test_auto_approval.is_safe_test_command(command)

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "echo hello",
            "git commit -m 'test'",
            "curl https://evil.com",
            "npx jest",
        ],
    )
    def test_rejects_non_test_commands(self, command):
        assert not invoke_test_auto_approval.is_safe_test_command(command)

    @pytest.mark.parametrize(
        "command",
        [
            "npm test; rm -rf /",
            "npm test | tee output.log",
            "npm test & echo done",
            "npm test < input.txt",
            "npm test > output.txt",
            "npm test $HOME",
            "npm test `whoami`",
            "npm test\nrm -rf /",
            "npm test\rrm -rf /",
        ],
    )
    def test_rejects_dangerous_metacharacters(self, command):
        assert not invoke_test_auto_approval.is_safe_test_command(command)

    def test_rejects_empty_command(self):
        assert not invoke_test_auto_approval.is_safe_test_command("")


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    def test_returns_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        assert invoke_test_auto_approval.main() == 0

    def test_returns_0_on_empty_input(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: ""),
        )
        assert invoke_test_auto_approval.main() == 0

    def test_returns_0_on_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: "not json"),
        )
        assert invoke_test_auto_approval.main() == 0

    def test_returns_0_when_no_command(self, monkeypatch):
        hook_input = json.dumps({"tool_input": {}})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        assert invoke_test_auto_approval.main() == 0

    def test_approves_safe_command(self, monkeypatch, capsys):
        hook_input = json.dumps(
            {"tool_input": {"command": "pytest tests/"}}
        )
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        assert invoke_test_auto_approval.main() == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "approve"

    def test_does_not_approve_unsafe_command(self, monkeypatch, capsys):
        hook_input = json.dumps(
            {"tool_input": {"command": "rm -rf /"}}
        )
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        assert invoke_test_auto_approval.main() == 0
        captured = capsys.readouterr()
        # Should not output an approval
        assert "approve" not in captured.out

    def test_returns_0_on_value_error(self, monkeypatch):
        """ValueError from stdin is caught and returns 0."""
        def raise_error():
            raise ValueError("bad value")

        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=raise_error),
        )
        assert invoke_test_auto_approval.main() == 0
