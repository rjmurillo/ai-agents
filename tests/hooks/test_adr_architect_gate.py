#!/usr/bin/env python3
"""Tests for the invoke_adr_architect_gate PreToolUse hook.

Covers: ADR file detection, architect evidence checking, blocking behavior,
exit codes (0=allow, 2=block), fail-open on errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse")
sys.path.insert(0, HOOK_DIR)

import invoke_adr_architect_gate  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for is_adr_file
# ---------------------------------------------------------------------------


class TestIsAdrFile:
    def test_matches_standard_adr(self):
        assert invoke_adr_architect_gate.is_adr_file("ADR-001-decision.md")

    def test_matches_nested_adr(self):
        assert invoke_adr_architect_gate.is_adr_file(
            ".agents/architecture/ADR-042.md"
        )

    def test_rejects_non_adr(self):
        assert not invoke_adr_architect_gate.is_adr_file("README.md")

    def test_rejects_empty(self):
        assert not invoke_adr_architect_gate.is_adr_file("")


# ---------------------------------------------------------------------------
# Unit tests for check_architect_evidence
# ---------------------------------------------------------------------------


class TestCheckArchitectEvidence:
    def test_finds_debate_log(self, tmp_path):
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        debate_log = analysis_dir / "debate-adr-001.md"
        debate_log.write_text("debate content")

        result = invoke_adr_architect_gate.check_architect_evidence(str(tmp_path))
        assert result["complete"] is True

    @patch("invoke_adr_architect_gate.get_today_session_log")
    def test_finds_session_evidence(self, mock_log, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(
            '{"notes": "Used /adr-review to validate changes"}'
        )
        mock_log.return_value = session_file

        result = invoke_adr_architect_gate.check_architect_evidence(str(tmp_path))
        assert result["complete"] is True

    @patch("invoke_adr_architect_gate.get_today_session_log", return_value=None)
    def test_no_evidence(self, _mock, tmp_path):
        result = invoke_adr_architect_gate.check_architect_evidence(str(tmp_path))
        assert result["complete"] is False


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_adr_architect_gate.main()
        assert result == 0

    def test_exits_0_on_empty_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        result = invoke_adr_architect_gate.main()
        assert result == 0

    def test_exits_0_on_invalid_json(self, mock_stdin: Callable[[str], None]):
        mock_stdin("not json")
        result = invoke_adr_architect_gate.main()
        assert result == 0

    def test_exits_0_for_non_edit_tool(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"},
                }
            )
        )
        result = invoke_adr_architect_gate.main()
        assert result == 0

    def test_exits_0_for_non_adr_file(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/project/README.md"},
                }
            )
        )
        result = invoke_adr_architect_gate.main()
        assert result == 0

    @patch("invoke_adr_architect_gate.check_architect_evidence")
    @patch("invoke_adr_architect_gate.get_project_directory", return_value="/project")
    def test_exits_0_when_evidence_exists(
        self,
        _mock_dir,
        mock_evidence,
        mock_stdin: Callable[[str], None],
    ):
        mock_evidence.return_value = {"complete": True, "evidence": "found"}
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/project/ADR-001.md"},
                }
            )
        )
        result = invoke_adr_architect_gate.main()
        assert result == 0

    @patch("invoke_adr_architect_gate.check_architect_evidence")
    @patch("invoke_adr_architect_gate.get_project_directory", return_value="/project")
    def test_exits_2_when_no_evidence(
        self,
        _mock_dir,
        mock_evidence,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        mock_evidence.return_value = {"complete": False, "reason": "none found"}
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/project/ADR-042.md"},
                }
            )
        )
        result = invoke_adr_architect_gate.main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "architect" in captured.out.lower()

    def test_exits_0_for_missing_file_path(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(
            json.dumps({"tool_name": "Edit", "tool_input": {"file_path": ""}})
        )
        result = invoke_adr_architect_gate.main()
        assert result == 0

    def test_exits_0_for_non_dict_tool_input(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"tool_name": "Edit", "tool_input": "string"}))
        result = invoke_adr_architect_gate.main()
        assert result == 0

    def test_fails_open_on_exception(self, mock_stdin: Callable[[str], None]):
        """PreToolUse hooks should fail-open on infrastructure errors."""
        mock_stdin(json.dumps({"tool_name": "Edit", "tool_input": None}))
        result = invoke_adr_architect_gate.main()
        assert result == 0
