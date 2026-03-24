"""Tests for UserPromptSubmit invoke_autonomous_execution_detector hook.

Verifies that autonomy keywords trigger protocol warnings,
and non-autonomy prompts pass through silently.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "UserPromptSubmit"
sys.path.insert(0, str(HOOK_DIR))

from invoke_autonomous_execution_detector import (  # noqa: E402
    AUTONOMY_PATTERNS,
    extract_prompt,
    has_autonomy_keywords,
    main,
)


class TestHasAutonomyKeywords:
    """Tests for autonomy keyword detection."""

    def test_autonomous(self) -> None:
        assert has_autonomy_keywords("Run this autonomous") is True

    def test_hands_off(self) -> None:
        assert has_autonomy_keywords("Please do this hands-off") is True

    def test_without_asking(self) -> None:
        assert has_autonomy_keywords("Do it without asking me") is True

    def test_without_confirmation(self) -> None:
        assert has_autonomy_keywords("Proceed without confirmation") is True

    def test_auto_prefix(self) -> None:
        assert has_autonomy_keywords("auto-execute this") is True
        assert has_autonomy_keywords("auto-run the tests") is True

    def test_unattended(self) -> None:
        assert has_autonomy_keywords("run unattended overnight") is True

    def test_run_autonomously(self) -> None:
        assert has_autonomy_keywords("Please run autonomously") is True

    def test_full_autonomy(self) -> None:
        assert has_autonomy_keywords("Use full autonomy") is True

    def test_no_human(self) -> None:
        assert has_autonomy_keywords("Do this with no human oversight") is True

    def test_no_verification(self) -> None:
        assert has_autonomy_keywords("Skip no verification needed") is True

    def test_blindly(self) -> None:
        assert has_autonomy_keywords("Apply changes blindly") is True

    def test_case_insensitive(self) -> None:
        assert has_autonomy_keywords("AUTONOMOUS mode please") is True
        assert has_autonomy_keywords("Run UNATTENDED") is True

    def test_no_keywords(self) -> None:
        assert has_autonomy_keywords("Please fix the bug in auth.py") is False

    def test_empty_string(self) -> None:
        assert has_autonomy_keywords("") is False

    def test_whitespace_only(self) -> None:
        assert has_autonomy_keywords("   ") is False

    def test_partial_word_no_match(self) -> None:
        """'autonomy' alone should not match 'autonomous' pattern."""
        assert has_autonomy_keywords("I want full autonomy") is True
        assert has_autonomy_keywords("automotive repair") is False


class TestExtractPrompt:
    """Tests for prompt extraction with schema fallbacks."""

    def test_prompt_key(self) -> None:
        result = extract_prompt({"prompt": "hello"})
        assert result == "hello"

    def test_user_message_text_key(self) -> None:
        result = extract_prompt({"user_message_text": "hello"})
        assert result == "hello"

    def test_message_key(self) -> None:
        result = extract_prompt({"message": "hello"})
        assert result == "hello"

    def test_priority_order(self) -> None:
        """prompt takes priority over user_message_text."""
        result = extract_prompt({"prompt": "first", "user_message_text": "second"})
        assert result == "first"

    def test_empty_prompt_falls_through(self) -> None:
        result = extract_prompt({"prompt": "", "user_message_text": "fallback"})
        assert result == "fallback"

    def test_whitespace_prompt_falls_through(self) -> None:
        result = extract_prompt({"prompt": "   ", "message": "fallback"})
        assert result == "fallback"

    def test_no_known_keys(self) -> None:
        assert extract_prompt({"other": "data"}) is None

    def test_non_string_value(self) -> None:
        assert extract_prompt({"prompt": 123}) is None

    def test_empty_dict(self) -> None:
        assert extract_prompt({}) is None


class TestAutonomyPatterns:
    """Tests for the patterns constant."""

    def test_patterns_not_empty(self) -> None:
        assert len(AUTONOMY_PATTERNS) > 0

    def test_all_patterns_are_compiled_regex(self) -> None:
        import re
        for pattern in AUTONOMY_PATTERNS:
            assert isinstance(pattern, re.Pattern)


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    target = "invoke_autonomous_execution_detector.skip_if_consumer_repo"
    with patch(target, return_value=False):
        yield


class TestMainAllow:
    """Tests for main() passing through."""

    def test_tty_stdin(self) -> None:
        with patch("invoke_autonomous_execution_detector.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_no_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"other": "data"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_normal_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"prompt": "Fix the auth bug"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_invalid_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        assert main() == 0


class TestMainDetect:
    """Tests for main() detecting autonomy keywords."""

    def test_autonomous_keyword_injects_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"prompt": "Run this autonomous"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        result = main()
        assert result == 0  # Non-blocking
        captured = capsys.readouterr()
        assert "Stricter protocol active" in captured.out

    def test_hands_off_keyword(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"prompt": "Do this hands-off please"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        main()
        captured = capsys.readouterr()
        assert "Stricter protocol active" in captured.out

    def test_user_message_text_schema(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"user_message_text": "Use full autonomy"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        main()
        captured = capsys.readouterr()
        assert "Stricter protocol active" in captured.out

    def test_message_schema(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"message": "Do it blindly"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        main()
        captured = capsys.readouterr()
        assert "Stricter protocol active" in captured.out


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_autonomous_execution_detector_as_script(self) -> None:
        import subprocess

        hook_path = str(
            HOOK_DIR / "invoke_autonomous_execution_detector.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input='{"prompt": "fix the bug"}',
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(HOOK_DIR / "invoke_autonomous_execution_detector.py")
        monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "fix the bug"}'))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
