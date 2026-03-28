#!/usr/bin/env python3
"""Tests for the invoke_adr_lifecycle_hook PostToolUse hook.

Covers: ADR file detection for Write/Edit/Bash, guidance output,
non-blocking exit code (always 0), edge cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PostToolUse")
sys.path.insert(0, HOOK_DIR)

import invoke_adr_lifecycle_hook  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for _is_adr_path
# ---------------------------------------------------------------------------


class TestIsAdrPath:
    def test_matches_standard_adr(self):
        assert invoke_adr_lifecycle_hook._is_adr_path("ADR-001-some-decision.md")

    def test_matches_nested_path(self):
        assert invoke_adr_lifecycle_hook._is_adr_path(
            ".agents/architecture/ADR-042-python-migration.md"
        )

    def test_rejects_non_adr(self):
        assert not invoke_adr_lifecycle_hook._is_adr_path("README.md")

    def test_rejects_empty(self):
        assert not invoke_adr_lifecycle_hook._is_adr_path("")


# ---------------------------------------------------------------------------
# Unit tests for _detect_adr_in_bash
# ---------------------------------------------------------------------------


class TestDetectAdrInBash:
    def test_detects_rm(self):
        assert invoke_adr_lifecycle_hook._detect_adr_in_bash("rm ADR-001.md")

    def test_detects_git_rm(self):
        assert invoke_adr_lifecycle_hook._detect_adr_in_bash("git rm ADR-042.md")

    def test_detects_mv(self):
        assert invoke_adr_lifecycle_hook._detect_adr_in_bash("mv ADR-001.md old/")

    def test_ignores_non_destructive(self):
        assert not invoke_adr_lifecycle_hook._detect_adr_in_bash("cat ADR-001.md")

    def test_ignores_non_adr(self):
        assert not invoke_adr_lifecycle_hook._detect_adr_in_bash("rm README.md")


# ---------------------------------------------------------------------------
# Unit tests for _detect_write_or_edit
# ---------------------------------------------------------------------------


class TestDetectWriteOrEdit:
    def test_detects_adr_file_path(self):
        result = invoke_adr_lifecycle_hook._detect_write_or_edit(
            {"file_path": "/project/ADR-001.md"}
        )
        assert result == "/project/ADR-001.md"

    def test_returns_none_for_non_adr(self):
        result = invoke_adr_lifecycle_hook._detect_write_or_edit(
            {"file_path": "/project/README.md"}
        )
        assert result is None

    def test_returns_none_for_missing_path(self):
        result = invoke_adr_lifecycle_hook._detect_write_or_edit({})
        assert result is None

    def test_returns_none_for_empty_path(self):
        result = invoke_adr_lifecycle_hook._detect_write_or_edit({"file_path": ""})
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_0_on_tty(self, monkeypatch):
        from unittest.mock import MagicMock

        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0

    def test_exits_0_on_empty_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0

    def test_exits_0_on_invalid_json(self, mock_stdin: Callable[[str], None]):
        mock_stdin("not json")
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0

    @patch("invoke_adr_lifecycle_hook.skip_if_consumer_repo", return_value=True)
    def test_exits_0_when_consumer_repo(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"tool_name": "Write", "tool_input": {}}))
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0

    def test_exits_0_for_non_adr_write(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/project/README.md"},
                }
            )
        )
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0

    def test_outputs_create_guidance_for_write(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/project/ADR-001.md"},
                }
            )
        )
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "File Created" in captured.out
        assert "/adr-review" in captured.out

    def test_outputs_edit_guidance_for_edit(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/project/ADR-042.md"},
                }
            )
        )
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "File Modified" in captured.out

    def test_outputs_delete_guidance_for_bash_rm(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "rm .agents/architecture/ADR-001.md"},
                }
            )
        )
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "File Removed" in captured.out

    def test_exits_0_for_non_matching_bash(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
            )
        )
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0

    def test_exits_0_for_non_dict_tool_input(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"tool_name": "Write", "tool_input": "string"}))
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0

    def test_always_exits_0_on_exception(
        self, mock_stdin: Callable[[str], None]
    ):
        """PostToolUse hooks must never block (always exit 0)."""
        mock_stdin(json.dumps({"tool_name": "Write", "tool_input": None}))
        result = invoke_adr_lifecycle_hook.main()
        assert result == 0
