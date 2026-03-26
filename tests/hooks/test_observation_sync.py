"""Tests for PostToolUse invoke_observation_sync hook.

Verifies that observation memories trigger Forgetful import,
non-observation memories are skipped, and errors are handled gracefully.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PostToolUse"
sys.path.insert(0, str(HOOK_DIR))

from invoke_observation_sync import (  # noqa: E402
    _find_observation_file,
    _is_observation_memory,
    main,
)


class TestIsObservationMemory:
    """Tests for observation memory detection."""

    def test_exact_suffix_match(self) -> None:
        result = _is_observation_memory({"name": "testing-observations"})
        assert result == "testing-observations"

    def test_domain_prefix_suffix(self) -> None:
        result = _is_observation_memory({"name": "git-hooks-observations"})
        assert result == "git-hooks-observations"

    def test_non_observation_memory(self) -> None:
        result = _is_observation_memory({"name": "architecture-decisions"})
        assert result is None

    def test_empty_name(self) -> None:
        result = _is_observation_memory({"name": ""})
        assert result is None

    def test_no_name_key(self) -> None:
        result = _is_observation_memory({})
        assert result is None

    def test_non_string_name(self) -> None:
        result = _is_observation_memory({"name": 42})
        assert result is None

    def test_observation_in_name_with_confidence_content(self) -> None:
        result = _is_observation_memory({
            "name": "skill-observations-v2",
            "content": "## Constraints (HIGH confidence)\n- rule",
        })
        assert result == "skill-observations-v2"

    def test_observation_in_name_without_confidence_content(self) -> None:
        result = _is_observation_memory({
            "name": "skill-observations-v2",
            "content": "just some text",
        })
        assert result is None


class TestFindObservationFile:
    """Tests for locating observation files on disk."""

    def test_exact_match(self, tmp_path: Path) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        obs_file = memories_dir / "testing-observations.md"
        obs_file.write_text("# Testing Observations")

        result = _find_observation_file(str(tmp_path), "testing-observations")
        assert result == obs_file

    def test_glob_match(self, tmp_path: Path) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        obs_file = memories_dir / "git-hooks-observations.md"
        obs_file.write_text("# Git Hooks Observations")

        result = _find_observation_file(str(tmp_path), "git-hooks-observations")
        assert result == obs_file

    def test_no_memories_dir(self, tmp_path: Path) -> None:
        result = _find_observation_file(str(tmp_path), "testing-observations")
        assert result is None

    def test_file_not_found(self, tmp_path: Path) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        result = _find_observation_file(str(tmp_path), "nonexistent-observations")
        assert result is None

    def test_rejects_path_traversal_dotdot(self, tmp_path: Path) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        result = _find_observation_file(str(tmp_path), "../../etc/passwd")
        assert result is None

    def test_rejects_path_traversal_slash(self, tmp_path: Path) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        result = _find_observation_file(str(tmp_path), "subdir/evil-observations")
        assert result is None

    def test_rejects_path_traversal_backslash(self, tmp_path: Path) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        result = _find_observation_file(str(tmp_path), "subdir\\evil-observations")
        assert result is None


class TestMainHook:
    """Tests for the main hook entry point."""

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=True)
    def test_skips_consumer_repo(self, mock_skip: MagicMock) -> None:
        assert main() == 0
        mock_skip.assert_called_once_with("observation-sync")

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=False)
    def test_exits_zero_on_empty_stdin(self, _mock: MagicMock) -> None:
        with patch("sys.stdin", io.StringIO("")):
            assert main() == 0

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=False)
    def test_exits_zero_on_non_observation(self, _mock: MagicMock) -> None:
        hook_input = json.dumps({
            "tool_name": "mcp__serena__write_memory",
            "tool_input": {"name": "architecture-decisions", "content": "some text"},
        })
        with patch("sys.stdin", io.StringIO(hook_input)):
            assert main() == 0

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=False)
    @patch("invoke_observation_sync._run_import")
    @patch("invoke_observation_sync._get_repo_root")
    def test_triggers_import_for_observation(
        self,
        mock_root: MagicMock,
        mock_import: MagicMock,
        _mock_skip: MagicMock,
        tmp_path: Path,
    ) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        obs_file = memories_dir / "testing-observations.md"
        obs_file.write_text("# Testing Observations")

        mock_root.return_value = str(tmp_path)

        hook_input = json.dumps({
            "tool_name": "mcp__serena__write_memory",
            "tool_input": {"name": "testing-observations", "content": "updated"},
        })
        with patch("sys.stdin", io.StringIO(hook_input)):
            assert main() == 0

        mock_import.assert_called_once_with(str(tmp_path), obs_file)

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=False)
    @patch("invoke_observation_sync._get_repo_root")
    def test_warns_when_file_not_found(
        self,
        mock_root: MagicMock,
        _mock_skip: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        mock_root.return_value = str(tmp_path)

        hook_input = json.dumps({
            "tool_name": "mcp__serena__write_memory",
            "tool_input": {"name": "missing-observations"},
        })
        with patch("sys.stdin", io.StringIO(hook_input)):
            assert main() == 0

        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "missing-observations" in captured.err

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=False)
    def test_exits_zero_on_invalid_json(self, _mock: MagicMock) -> None:
        with patch("sys.stdin", io.StringIO("not json")):
            assert main() == 0

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=False)
    def test_exits_zero_when_tool_input_not_dict(self, _mock: MagicMock) -> None:
        hook_input = json.dumps({
            "tool_name": "mcp__serena__write_memory",
            "tool_input": "string_input",
        })
        with patch("sys.stdin", io.StringIO(hook_input)):
            assert main() == 0

    @patch("invoke_observation_sync.skip_if_consumer_repo", return_value=False)
    def test_exits_zero_on_tty_stdin(self, _mock: MagicMock) -> None:
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        with patch("sys.stdin", mock_stdin):
            assert main() == 0
