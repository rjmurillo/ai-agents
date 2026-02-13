"""Tests for invoke_autonomous_execution_detector.py UserPromptSubmit hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "UserPromptSubmit"),
)

from invoke_autonomous_execution_detector import (
    extract_prompt,
    has_autonomy_keywords,
    main,
)


class TestAutonomyKeywords:
    @pytest.mark.parametrize(
        "prompt",
        [
            "Run this autonomous task",
            "Do it hands-off please",
            "Complete without asking me",
            "Execute without confirmation",
            "auto-execute the pipeline",
            "auto-run the tests",
            "Run it unattended",
            "Run autonomously through the list",
            "Give full autonomy to the agent",
            "Complete with no human in the loop",
            "Proceed with no verification",
            "Just blindly apply all changes",
        ],
    )
    def test_detects_autonomy_keywords(self, prompt: str) -> None:
        assert has_autonomy_keywords(prompt) is True

    @pytest.mark.parametrize(
        "prompt",
        [
            "Please fix this bug",
            "Add a new feature",
            "Run the tests",
            "Review the PR",
            "",
            "   ",
        ],
    )
    def test_does_not_trigger_on_normal_prompts(self, prompt: str) -> None:
        assert has_autonomy_keywords(prompt) is False

    def test_returns_false_for_none_equivalent(self) -> None:
        assert has_autonomy_keywords("") is False


class TestExtractPrompt:
    def test_extracts_from_prompt_field(self) -> None:
        assert extract_prompt({"prompt": "hello"}) == "hello"

    def test_extracts_from_user_message_text(self) -> None:
        assert extract_prompt({"user_message_text": "hello"}) == "hello"

    def test_extracts_from_message_field(self) -> None:
        assert extract_prompt({"message": "hello"}) == "hello"

    def test_prefers_prompt_over_others(self) -> None:
        data = {"prompt": "first", "user_message_text": "second", "message": "third"}
        assert extract_prompt(data) == "first"

    def test_returns_none_for_empty(self) -> None:
        assert extract_prompt({}) is None

    def test_returns_none_for_whitespace_only(self) -> None:
        assert extract_prompt({"prompt": "  "}) is None


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

    def test_returns_zero_for_prompt_without_keywords(self) -> None:
        input_data = json.dumps({"prompt": "Fix the bug in login"})
        with patch("sys.stdin", StringIO(input_data)):
            assert main() == 0

    def test_outputs_protocol_message_for_autonomy_keyword(self) -> None:
        input_data = json.dumps({"prompt": "Run this autonomous task"})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "Stricter protocol active" in mock_stdout.getvalue()

    def test_no_output_for_normal_prompt(self) -> None:
        input_data = json.dumps({"prompt": "Fix the tests"})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert mock_stdout.getvalue() == ""

    def test_returns_zero_for_empty_prompt(self) -> None:
        input_data = json.dumps({"prompt": ""})
        with patch("sys.stdin", StringIO(input_data)):
            assert main() == 0

    def test_handles_user_message_text_field(self) -> None:
        input_data = json.dumps({"user_message_text": "Execute this unattended"})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "Stricter protocol active" in mock_stdout.getvalue()
