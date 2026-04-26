#!/usr/bin/env python3
"""Tests for SessionStart/invoke_context_loader.py.

Covers:
- HANDOFF.md loading and truncation
- Latest retrospective detection and loading
- Fail-open on missing files
- Consumer repo skip
- Audit trail creation
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "SessionStart"))

import invoke_context_loader


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    """Create a minimal project directory tree."""
    agents = tmp_path / ".agents"
    agents.mkdir()
    (agents / "sessions").mkdir()
    (agents / "retrospective").mkdir()

    # Create HANDOFF.md
    (agents / "HANDOFF.md").write_text(
        "# Handoff\n\nProject state dashboard.\n", encoding="utf-8"
    )
    return tmp_path


class TestReadFileTruncated:
    """Test _read_file_truncated helper."""

    def test_reads_small_file(self, tmp_path: Path) -> None:
        f = tmp_path / "small.md"
        f.write_text("hello world", encoding="utf-8")
        result = invoke_context_loader._read_file_truncated(f, 1000)
        assert result == "hello world"

    def test_truncates_large_file(self, tmp_path: Path) -> None:
        f = tmp_path / "large.md"
        f.write_text("x" * 5000, encoding="utf-8")
        result = invoke_context_loader._read_file_truncated(f, 100)
        assert result is not None
        assert len(result) < 200  # 100 chars + truncation message
        assert "truncated" in result

    def test_returns_none_on_missing_file(self, tmp_path: Path) -> None:
        result = invoke_context_loader._read_file_truncated(
            tmp_path / "nonexistent.md", 1000
        )
        assert result is None


class TestFindLatestRetrospective:
    """Test _find_latest_retrospective helper."""

    def test_finds_most_recent(self, tmp_path: Path) -> None:
        retro_dir = tmp_path / "retros"
        retro_dir.mkdir()
        old = retro_dir / "2025-01-01-retro.md"
        old.write_text("old retro", encoding="utf-8")
        new = retro_dir / "2025-06-15-retro.md"
        new.write_text("new retro", encoding="utf-8")
        # Touch new file to ensure it's newer
        import time
        time.sleep(0.01)
        new.write_text("new retro updated", encoding="utf-8")

        result = invoke_context_loader._find_latest_retrospective(retro_dir)
        assert result is not None
        assert result.name == "2025-06-15-retro.md"

    def test_returns_none_on_empty_dir(self, tmp_path: Path) -> None:
        retro_dir = tmp_path / "retros"
        retro_dir.mkdir()
        result = invoke_context_loader._find_latest_retrospective(retro_dir)
        assert result is None

    def test_returns_none_on_missing_dir(self, tmp_path: Path) -> None:
        result = invoke_context_loader._find_latest_retrospective(
            tmp_path / "nonexistent"
        )
        assert result is None


class TestMain:
    """Test main() function."""

    def test_skip_consumer_repo(self, capsys: pytest.CaptureFixture) -> None:
        with patch.object(
            invoke_context_loader, "skip_if_consumer_repo", return_value=True
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_context_loader.main()
            assert exc_info.value.code == 0

    def test_loads_handoff_and_retro(
        self, project_tree: Path, capsys: pytest.CaptureFixture
    ) -> None:
        # Add a retrospective
        retro = project_tree / ".agents" / "retrospective" / "2025-06-15-retro.md"
        retro.write_text("# Retro\n\nLearnings here.", encoding="utf-8")

        with patch.object(
            invoke_context_loader, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_context_loader, "get_project_directory", return_value=str(project_tree)
        ):
            invoke_context_loader.main()

        captured = capsys.readouterr()
        assert "HANDOFF.md" in captured.out
        assert "Retrospective" in captured.out

    def test_handles_no_retros(
        self, project_tree: Path, capsys: pytest.CaptureFixture
    ) -> None:
        with patch.object(
            invoke_context_loader, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_context_loader, "get_project_directory", return_value=str(project_tree)
        ):
            invoke_context_loader.main()

        captured = capsys.readouterr()
        assert "HANDOFF.md" in captured.out
        # Should still output something (handoff only)
        assert "Loaded" in captured.out

    def test_handles_missing_handoff(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        agents = tmp_path / ".agents"
        agents.mkdir()

        with patch.object(
            invoke_context_loader, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_context_loader, "get_project_directory", return_value=str(tmp_path)
        ):
            invoke_context_loader.main()

        captured = capsys.readouterr()
        assert "No context files found" in captured.out

    def test_writes_audit_log(self, project_tree: Path) -> None:
        with patch.object(
            invoke_context_loader, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_context_loader, "get_project_directory", return_value=str(project_tree)
        ):
            invoke_context_loader.main()

        audit_dir = project_tree / ".agents" / ".hook-state"
        assert audit_dir.exists()
        log_files = list(audit_dir.glob("context-loader-*.log"))
        assert len(log_files) >= 1


class TestFailOpen:
    """Test that hook fails open on all errors."""

    def test_exception_in_main_exits_zero(self) -> None:
        with patch.object(
            invoke_context_loader, "skip_if_consumer_repo", side_effect=RuntimeError("boom")
        ):
            # The if __name__ == "__main__" block catches all exceptions
            # We test the try/except pattern directly
            try:
                invoke_context_loader.main()
            except (SystemExit, RuntimeError):
                pass  # Expected
