"""Tests for UserPromptSubmit invoke_serena_reassertion hook.

Verifies that the Serena re-assertion reminder is injected on every
valid prompt (positive), and that malformed, empty, tty, and
no-prompt input pass through silently with exit code 0 (negative/edge).

The hook is stateless and unconditional by design (see the hook
docstring): it does not branch on a Serena activation marker because no
such marker surface exists for a UserPromptSubmit hook. These tests
assert that contract: a reminder on every real prompt, no crash on bad
input, never blocking.
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

from invoke_serena_reassertion import (  # noqa: E402
    SERENA_REMINDER,
    build_reminder,
    extract_prompt,
    main,
)


class TestBuildReminder:
    """Tests for the reminder builder."""

    def test_returns_reminder_constant(self) -> None:
        assert build_reminder() == SERENA_REMINDER

    def test_reminder_mentions_serena(self) -> None:
        assert "Serena" in build_reminder()

    def test_reminder_names_symbolic_tools(self) -> None:
        """Reminder re-asserts the symbolic-tools preference (issue #1993)."""
        reminder = build_reminder()
        assert "find_symbol" in reminder
        assert "get_symbols_overview" in reminder

    def test_reminder_names_recovery_action(self) -> None:
        """Reminder names initial_instructions as the recovery action."""
        assert "initial_instructions" in build_reminder()

    def test_reminder_discourages_native_tools(self) -> None:
        assert "Read/Edit/Bash" in build_reminder()

    def test_reminder_no_dashes(self) -> None:
        """Universal rule: no em/en dashes in authored text."""
        assert "—" not in build_reminder()
        assert "–" not in build_reminder()


class TestExtractPrompt:
    """Tests for prompt extraction with schema fallbacks."""

    def test_prompt_key(self) -> None:
        assert extract_prompt({"prompt": "hello"}) == "hello"

    def test_user_message_text_key(self) -> None:
        assert extract_prompt({"user_message_text": "hello"}) == "hello"

    def test_message_key(self) -> None:
        assert extract_prompt({"message": "hello"}) == "hello"

    def test_priority_order(self) -> None:
        """prompt takes priority over user_message_text."""
        assert extract_prompt({"prompt": "first", "user_message_text": "second"}) == "first"

    def test_empty_prompt_falls_through(self) -> None:
        assert extract_prompt({"prompt": "", "user_message_text": "fallback"}) == "fallback"

    def test_whitespace_prompt_falls_through(self) -> None:
        assert extract_prompt({"prompt": "   ", "message": "fallback"}) == "fallback"

    def test_no_known_keys(self) -> None:
        assert extract_prompt({"other": "data"}) is None

    def test_non_string_value(self) -> None:
        assert extract_prompt({"prompt": 123}) is None

    def test_empty_dict(self) -> None:
        assert extract_prompt({}) is None


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    target = "invoke_serena_reassertion.skip_if_consumer_repo"
    with patch(target, return_value=False):
        yield


class TestMainInjects:
    """Positive: main() injects the reminder on a valid prompt."""

    def test_valid_prompt_injects_reminder(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"prompt": "fix the auth bug"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        result = main()
        assert result == 0  # Non-blocking, always
        captured = capsys.readouterr()
        assert "Serena re-assertion" in captured.out

    def test_injects_regardless_of_prompt_content(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Unconditional: any non-empty prompt triggers the reminder."""
        data = json.dumps({"prompt": "what is the weather"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        main()
        captured = capsys.readouterr()
        assert "find_symbol" in captured.out

    def test_user_message_text_schema(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"user_message_text": "refactor module"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        main()
        captured = capsys.readouterr()
        assert "Serena re-assertion" in captured.out

    def test_message_schema(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"message": "add a test"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        main()
        captured = capsys.readouterr()
        assert "Serena re-assertion" in captured.out


class TestMainPassesThrough:
    """Negative/edge: main() stays silent and returns 0 on bad input."""

    def test_tty_stdin(self) -> None:
        with patch("invoke_serena_reassertion.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0
        assert capsys.readouterr().out == ""

    def test_whitespace_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("   \n  "))
        assert main() == 0
        assert capsys.readouterr().out == ""

    def test_invalid_json_fails_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        assert main() == 0
        assert capsys.readouterr().out == ""

    def test_non_dict_json(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """A JSON array (not an object) must not crash or inject."""
        monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2, 3]"))
        assert main() == 0
        assert capsys.readouterr().out == ""

    def test_no_prompt_key(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"other": "data"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0
        assert capsys.readouterr().out == ""

    def test_empty_prompt_value(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        data = json.dumps({"prompt": ""})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0
        assert capsys.readouterr().out == ""


class TestConsumerRepoSkip:
    """Edge: skip silently in a consumer repo (no .agents/)."""

    def test_skip_when_consumer_repo(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        with patch("invoke_serena_reassertion.skip_if_consumer_repo", return_value=True):
            data = json.dumps({"prompt": "fix the bug"})
            monkeypatch.setattr("sys.stdin", io.StringIO(data))
            assert main() == 0
            assert "Serena re-assertion" not in capsys.readouterr().out


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_serena_reassertion_as_script(self) -> None:
        import subprocess

        hook_path = str(HOOK_DIR / "invoke_serena_reassertion.py")
        result = subprocess.run(
            ["python3", hook_path],
            input='{"prompt": "fix the bug"}',
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Serena re-assertion" in result.stdout

    def test_main_guard_via_runpy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(HOOK_DIR / "invoke_serena_reassertion.py")
        monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "fix the bug"}'))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
