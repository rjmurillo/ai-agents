"""Tests for invoke_test_auto_approval.py PermissionRequest hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "PermissionRequest"),
)

from invoke_test_auto_approval import (
    get_command_from_input,
    is_safe_test_command,
    main,
)


class TestGetCommandFromInput:
    def test_extracts_command(self) -> None:
        hook_input: dict[str, object] = {"tool_input": {"command": "pytest tests/"}}
        assert get_command_from_input(hook_input) == "pytest tests/"

    def test_returns_none_for_missing_tool_input(self) -> None:
        assert get_command_from_input({}) is None

    def test_returns_none_for_missing_command(self) -> None:
        assert get_command_from_input({"tool_input": {}}) is None

    def test_returns_none_for_empty_command(self) -> None:
        assert get_command_from_input({"tool_input": {"command": "  "}}) is None

    def test_strips_whitespace(self) -> None:
        hook_input: dict[str, object] = {"tool_input": {"command": "  pytest  "}}
        assert get_command_from_input(hook_input) == "pytest"

    def test_returns_none_for_non_dict_tool_input(self) -> None:
        assert get_command_from_input({"tool_input": "string"}) is None


class TestIsSafeTestCommand:
    @pytest.mark.parametrize(
        "command",
        [
            "pwsh -Command Invoke-Pester",
            "pwsh ./tests/run.ps1 Invoke-Pester",
            "npm test",
            "npm run test",
            "pnpm test",
            "yarn test",
            "pytest",
            "pytest tests/",
            "pytest -v tests/test_foo.py",
            "python -m pytest",
            "python -m pytest tests/",
            "dotnet test",
            "dotnet test ./MyProject.Tests",
            "mvn test",
            "gradle test",
            "cargo test",
            "go test ./...",
        ],
    )
    def test_approves_safe_commands(self, command: str) -> None:
        assert is_safe_test_command(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "echo hello",
            "ls -la",
            "curl http://example.com",
            "git push --force",
        ],
    )
    def test_rejects_non_test_commands(self, command: str) -> None:
        assert is_safe_test_command(command) is False

    @pytest.mark.parametrize(
        "command",
        [
            "npm test; rm -rf /",
            "pytest | cat",
            "npm test && echo pwned",
            "npm test < /etc/passwd",
            "npm test > /tmp/out",
            "pytest $HOME",
            "pytest `whoami`",
            "pytest\nrm -rf /",
        ],
    )
    def test_rejects_commands_with_metacharacters(self, command: str) -> None:
        assert is_safe_test_command(command) is False


class TestMain:
    def test_returns_zero_when_stdin_is_tty(self) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_returns_zero_for_empty_input(self) -> None:
        with patch("sys.stdin", StringIO("")):
            assert main() == 0

    def test_returns_zero_for_invalid_json(self) -> None:
        with patch("sys.stdin", StringIO("not json")):
            assert main() == 0

    def test_returns_zero_for_missing_command(self) -> None:
        input_data = json.dumps({"tool_input": {}})
        with patch("sys.stdin", StringIO(input_data)):
            assert main() == 0

    def test_outputs_approve_for_safe_command(self) -> None:
        input_data = json.dumps({"tool_input": {"command": "pytest tests/"}})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            output = json.loads(mock_stdout.getvalue().strip())
            assert output["decision"] == "approve"
            assert "Auto-approved" in output["reason"]

    def test_no_output_for_non_test_command(self) -> None:
        input_data = json.dumps({"tool_input": {"command": "rm -rf /"}})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert mock_stdout.getvalue().strip() == ""

    def test_no_output_for_command_with_injection(self) -> None:
        input_data = json.dumps({"tool_input": {"command": "npm test; rm -rf /"}})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert mock_stdout.getvalue().strip() == ""

    def test_approves_dotnet_test(self) -> None:
        input_data = json.dumps({"tool_input": {"command": "dotnet test ./MyProject"}})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            output = json.loads(mock_stdout.getvalue().strip())
            assert output["decision"] == "approve"
