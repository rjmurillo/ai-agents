"""Tests for invoke_research_then_implement.py UserPromptSubmit hook."""

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

from invoke_research_then_implement import (
    build_research_guidance,
    detect_complexity,
    extract_prompt,
    main,
)


class TestDetectComplexity:
    @pytest.mark.parametrize(
        ("prompt", "expected_reason"),
        [
            ("Create a new subsystem for event processing", "new subsystem"),
            ("Build a new service for notifications", "new subsystem"),
            ("Add a new module for data ingestion", "new subsystem"),
            ("We need to redesign the API layer", "architectural change"),
            ("Rearchitect the storage backend", "architectural change"),
            ("This requires cross-repo changes to shared libs", "cross-repo change"),
            ("Implement multi-repo deployment pipeline", "cross-repo change"),
            ("Add OAuth support to the login flow", "security-sensitive"),
            ("Implement MFA for admin accounts", "security-sensitive"),
            ("Add JWT validation to the gateway", "security-sensitive"),
            ("Migrate the database from Postgres to Cosmos", "migration"),
            ("We need a breaking change to the API contract", "breaking change"),
            ("Deprecate the v1 endpoints", "breaking change"),
            ("There are multiple approaches we could take", "multiple approaches"),
            ("Need to evaluate the trade-off between speed and safety", "multiple approaches"),
            ("This is unfamiliar territory for the team", "unfamiliar domain"),
            ("First time working with gRPC in this repo", "unfamiliar domain"),
        ],
    )
    def test_detects_complexity_signals(self, prompt: str, expected_reason: str) -> None:
        reasons = detect_complexity(prompt)
        assert expected_reason in reasons

    @pytest.mark.parametrize(
        "prompt",
        [
            "Fix the bug in the login page",
            "Update docs for the new API",
            "Bump version to 2.0",
            "Rename the variable",
            "Reformat the config file",
            "Fix typo in error message text",
            "Fix lint warnings in the test file",
        ],
    )
    def test_skip_patterns_suppress_detection(self, prompt: str) -> None:
        assert detect_complexity(prompt) == []

    def test_returns_empty_for_short_prompt(self) -> None:
        assert detect_complexity("new service") == []

    def test_returns_empty_for_empty_string(self) -> None:
        assert detect_complexity("") == []

    def test_returns_empty_for_none(self) -> None:
        assert detect_complexity(None) == []

    def test_detects_multiple_signals(self) -> None:
        prompt = "We need to migrate authentication to a new subsystem with OAuth"
        reasons = detect_complexity(prompt)
        assert len(reasons) >= 2
        assert "migration" in reasons
        assert "security-sensitive" in reasons


class TestBuildResearchGuidance:
    def test_includes_all_reasons(self) -> None:
        msg = build_research_guidance(["new subsystem", "migration"])
        assert "new subsystem" in msg
        assert "migration" in msg

    def test_includes_action_steps(self) -> None:
        msg = build_research_guidance(["architectural change"])
        assert "Search Serena memories" in msg
        assert "constraints" in msg
        assert "plan or spec" in msg


class TestExtractPrompt:
    def test_extracts_from_prompt_field(self) -> None:
        assert extract_prompt({"prompt": "hello"}) == "hello"

    def test_extracts_from_user_message_text(self) -> None:
        assert extract_prompt({"user_message_text": "hello"}) == "hello"

    def test_extracts_from_message_field(self) -> None:
        assert extract_prompt({"message": "hello"}) == "hello"

    def test_prefers_prompt_over_others(self) -> None:
        data: dict[str, object] = {
            "prompt": "first",
            "user_message_text": "second",
            "message": "third",
        }
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

    def test_returns_zero_for_prompt_without_complexity(self) -> None:
        input_data = json.dumps({"prompt": "Please run the test suite for me"})
        with patch("sys.stdin", StringIO(input_data)):
            assert main() == 0

    def test_outputs_guidance_for_complex_prompt(self) -> None:
        input_data = json.dumps({"prompt": "Create a new subsystem for event processing"})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            output = mock_stdout.getvalue()
            assert "Research-then-Implement advisory" in output
            assert "new subsystem" in output

    def test_no_output_for_simple_prompt(self) -> None:
        input_data = json.dumps({"prompt": "Fix the tests and make them pass"})
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert mock_stdout.getvalue() == ""

    def test_no_output_for_skip_pattern_prompt(self) -> None:
        input_data = json.dumps({"prompt": "Fix bug in the authentication module handler"})
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
        input_data = json.dumps(
            {"user_message_text": "Migrate the entire database to a new schema design"}
        )
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "Research-then-Implement advisory" in mock_stdout.getvalue()
