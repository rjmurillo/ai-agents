#!/usr/bin/env python3
"""Tests for the invoke_skill_learning Stop hook.

Covers: main entry point, skill detection, learning extraction,
non-blocking exit code (always 0), path validation, consumer repo skip.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "Stop")
sys.path.insert(0, HOOK_DIR)

import invoke_skill_learning  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for _validate_path_string
# ---------------------------------------------------------------------------


class TestValidatePathString:
    def test_accepts_normal_path(self):
        assert invoke_skill_learning._validate_path_string("/tmp/project") == "/tmp/project"

    def test_rejects_null_byte(self):
        assert invoke_skill_learning._validate_path_string("/tmp/\x00evil") is None

    def test_rejects_newline(self):
        assert invoke_skill_learning._validate_path_string("/tmp/\nevil") is None

    def test_rejects_tab(self):
        assert invoke_skill_learning._validate_path_string("/tmp/\tevil") is None

    def test_rejects_traversal(self):
        assert invoke_skill_learning._validate_path_string("../../etc/passwd") is None

    def test_rejects_non_string(self):
        assert invoke_skill_learning._validate_path_string(123) is None


# ---------------------------------------------------------------------------
# Unit tests for _is_relative_to
# ---------------------------------------------------------------------------


class TestIsRelativeTo:
    def test_child_is_relative(self, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        assert invoke_skill_learning._is_relative_to(child, tmp_path)

    def test_unrelated_is_not_relative(self, tmp_path):
        other = Path("/completely/different/path")
        assert not invoke_skill_learning._is_relative_to(other, tmp_path)


# ---------------------------------------------------------------------------
# Unit tests for get_conversation_messages
# ---------------------------------------------------------------------------


class TestGetConversationMessages:
    def test_extracts_messages(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = invoke_skill_learning.get_conversation_messages({"messages": msgs})
        assert result == msgs

    def test_returns_empty_when_missing(self):
        result = invoke_skill_learning.get_conversation_messages({})
        assert result == []


# ---------------------------------------------------------------------------
# Unit tests for detect_skill_usage
# ---------------------------------------------------------------------------


class TestDetectSkillUsage:
    def test_detects_skill_path_reference(self):
        messages = [
            {"role": "user", "content": "Check .claude/skills/reflect/SKILL.md"},
            {"role": "assistant", "content": "Using .claude/skills/reflect/SKILL.md"},
        ]
        result = invoke_skill_learning.detect_skill_usage(messages)
        assert "reflect" in result

    def test_returns_empty_for_no_skills(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = invoke_skill_learning.detect_skill_usage(messages)
        assert result == {}


# ---------------------------------------------------------------------------
# Unit tests for check_skill_context
# ---------------------------------------------------------------------------


class TestCheckSkillContext:
    def test_finds_skill_name(self):
        assert invoke_skill_learning.check_skill_context(
            "Used the reflect skill", "reflect"
        )

    def test_finds_skill_path(self):
        assert invoke_skill_learning.check_skill_context(
            "See .claude/skills/reflect/SKILL.md", "reflect"
        )

    def test_returns_false_when_absent(self):
        assert not invoke_skill_learning.check_skill_context(
            "Nothing relevant here", "reflect"
        )


# ---------------------------------------------------------------------------
# Unit tests for write_learning_notification
# ---------------------------------------------------------------------------


class TestWriteLearningNotification:
    def test_outputs_notification(self, capsys):
        invoke_skill_learning.write_learning_notification("reflect", 1, 2, 0)
        captured = capsys.readouterr()
        assert "reflect" in captured.out
        assert "1 HIGH" in captured.out

    def test_no_output_when_zero(self, capsys):
        invoke_skill_learning.write_learning_notification("reflect", 0, 0, 0)
        captured = capsys.readouterr()
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=True)
    def test_exits_0_when_consumer_repo(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("{}")
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_tty(self, _mock, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_empty_input(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("")
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_invalid_json(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("not json")
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_with_no_messages(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"cwd": "/tmp/test", "messages": []}))
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    @patch("invoke_skill_learning.detect_skill_usage", return_value={})
    @patch("invoke_skill_learning.get_safe_project_path")
    def test_exits_0_when_no_skills_detected(
        self,
        mock_safe_path,
        _detect,
        _skip,
        mock_stdin: Callable[[str], None],
        tmp_path,
    ):
        mock_safe_path.return_value = tmp_path
        mock_stdin(
            json.dumps(
                {
                    "cwd": str(tmp_path),
                    "messages": [{"role": "user", "content": "hello"}],
                }
            )
        )
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_always_exits_0_on_exception(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        """Stop hooks must never block (always exit 0)."""
        mock_stdin(json.dumps({"cwd": None, "messages": "not a list"}))
        result = invoke_skill_learning.main()
        assert result == 0
