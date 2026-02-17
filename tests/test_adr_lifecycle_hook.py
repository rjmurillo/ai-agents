"""Tests for the ADR lifecycle PostToolUse hook.

Verifies that the hook correctly detects ADR file creation, modification,
and deletion operations and injects appropriate guidance.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = str(
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "hooks"
    / "PostToolUse"
    / "invoke_adr_lifecycle_hook.py"
)


def _run_hook(tool_name: str, tool_input: dict) -> subprocess.CompletedProcess:
    """Run the hook with simulated Claude Code input."""
    hook_input = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, HOOK_SCRIPT],
        input=hook_input,
        capture_output=True,
        text=True,
    )


class TestADRDetection:
    """Verify ADR file change detection across tool types."""

    def test_write_adr_file_injects_guidance(self) -> None:
        result = _run_hook("Write", {"file_path": ".agents/architecture/ADR-047-test.md"})
        assert result.returncode == 0
        assert "ADR Change Detected" in result.stdout
        assert "/adr-review" in result.stdout

    def test_edit_adr_file_injects_guidance(self) -> None:
        result = _run_hook("Edit", {"file_path": ".agents/architecture/ADR-012-something.md"})
        assert result.returncode == 0
        assert "ADR Change Detected" in result.stdout
        assert "Modified" in result.stdout

    def test_bash_rm_adr_injects_guidance(self) -> None:
        result = _run_hook("Bash", {"command": "rm .agents/architecture/ADR-012-old.md"})
        assert result.returncode == 0
        assert "ADR Change Detected" in result.stdout
        assert "Removed" in result.stdout

    def test_bash_git_rm_adr_injects_guidance(self) -> None:
        result = _run_hook("Bash", {"command": "git rm .agents/architecture/ADR-005-deprecated.md"})
        assert result.returncode == 0
        assert "ADR Change Detected" in result.stdout

    def test_bash_mv_adr_injects_guidance(self) -> None:
        result = _run_hook("Bash", {"command": "mv ADR-001-old.md ADR-001-renamed.md"})
        assert result.returncode == 0
        assert "ADR Change Detected" in result.stdout


class TestNonADRIgnored:
    """Verify non-ADR operations produce no output."""

    def test_write_non_adr_file_no_output(self) -> None:
        result = _run_hook("Write", {"file_path": "src/main.py"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_edit_non_adr_file_no_output(self) -> None:
        result = _run_hook("Edit", {"file_path": "README.md"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_bash_non_adr_command_no_output(self) -> None:
        result = _run_hook("Bash", {"command": "git status"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_bash_rm_non_adr_no_output(self) -> None:
        result = _run_hook("Bash", {"command": "rm some_file.txt"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestEdgeCases:
    """Verify robustness for malformed or empty input."""

    def test_empty_stdin_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, HOOK_SCRIPT],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_invalid_json_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, HOOK_SCRIPT],
            input="not json",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_missing_tool_input_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, HOOK_SCRIPT],
            input=json.dumps({"tool_name": "Write"}),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_missing_file_path_exits_zero(self) -> None:
        result = _run_hook("Write", {"content": "some content"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    @pytest.mark.parametrize(
        "file_path",
        [
            "ADR-123.md",
            "docs/ADR-001-title.md",
            ".agents/architecture/ADR-999-something.md",
        ],
    )
    def test_adr_pattern_matches_various_paths(self, file_path: str) -> None:
        result = _run_hook("Edit", {"file_path": file_path})
        assert result.returncode == 0
        assert "ADR Change Detected" in result.stdout
