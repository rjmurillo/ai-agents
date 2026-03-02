#!/usr/bin/env python3
"""Tests for detect_adr_changes module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/adr-review/scripts/detect_adr_changes.py")

get_adr_status = mod.get_adr_status
get_dependent_adrs = mod.get_dependent_adrs
run_git = mod.run_git
detect_adr_changes = mod.detect_adr_changes
main = mod.main


class TestGetAdrStatus:
    """Tests for get_adr_status function."""

    def test_returns_unknown_for_missing_file(self, tmp_path: Path) -> None:
        result = get_adr_status(str(tmp_path / "nonexistent.md"))
        assert result == "unknown"

    def test_extracts_status_from_frontmatter(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: accepted\n---\n# Title\n")
        result = get_adr_status(str(adr))
        assert result == "accepted"

    def test_returns_proposed_when_no_status(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("# ADR-001\nSome content\n")
        result = get_adr_status(str(adr))
        assert result == "proposed"

    def test_normalizes_status_to_lowercase(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: DEPRECATED\n---\n")
        result = get_adr_status(str(adr))
        assert result == "deprecated"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus:   accepted  \n---\n")
        result = get_adr_status(str(adr))
        assert result == "accepted"


class TestGetDependentAdrs:
    """Tests for get_dependent_adrs function."""

    def test_finds_references(self, tmp_path: Path) -> None:
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001\nReferences ADR-002")
        (arch_dir / "ADR-002.md").write_text("# ADR-002\nNo references")
        result = get_dependent_adrs("ADR-002", str(tmp_path))
        # Note: get_dependent_adrs returns all files containing the search string,
        # including the ADR's own file (ADR-002.md contains "ADR-002" in its title).
        assert len(result) == 2
        names = [Path(r).name for r in result]
        assert "ADR-001.md" in names
        assert "ADR-002.md" in names

    def test_returns_empty_for_no_references(self, tmp_path: Path) -> None:
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001\nNo references")
        result = get_dependent_adrs("ADR-999", str(tmp_path))
        assert result == []

    def test_handles_missing_directory(self, tmp_path: Path) -> None:
        result = get_dependent_adrs("ADR-001", str(tmp_path))
        assert result == []


class TestRunGit:
    """Tests for run_git function."""

    def test_returns_output_on_success(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        returncode, output = run_git(["status"], cwd=str(tmp_path))
        assert returncode == 0

    def test_returns_error_code_on_failure(self, tmp_path: Path) -> None:
        returncode, output = run_git(
            ["log", "--oneline", "-1"],
            cwd=str(tmp_path),
        )
        assert returncode != 0

    @patch("subprocess.run", side_effect=FileNotFoundError())
    def test_handles_missing_git(self, mock_run: MagicMock) -> None:
        returncode, output = run_git(["status"], cwd="/tmp")
        assert returncode == -1
        assert "git not found" in output


class TestDetectAdrChanges:
    """Tests for detect_adr_changes function."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("init")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        # Add a second commit so HEAD~1 is valid
        (tmp_path / "README.md").write_text("updated")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "update readme"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        return tmp_path

    def test_no_changes(self, git_repo: Path) -> None:
        result = detect_adr_changes(str(git_repo), since_commit="HEAD~1")
        assert result["HasChanges"] is False
        assert result["RecommendedAction"] == "none"
        assert result["Created"] == []
        assert result["Modified"] == []
        assert result["Deleted"] == []

    def test_detects_created_adr(self, git_repo: Path) -> None:
        arch_dir = git_repo / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001")
        subprocess.run(["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add ADR"],
            cwd=str(git_repo),
            capture_output=True,
            check=True,
        )
        result = detect_adr_changes(str(git_repo), since_commit="HEAD~1")
        assert result["HasChanges"] is True
        assert len(result["Created"]) == 1
        assert result["RecommendedAction"] == "review"

    def test_result_has_timestamp(self, git_repo: Path) -> None:
        result = detect_adr_changes(str(git_repo), since_commit="HEAD~1")
        assert "Timestamp" in result
        assert "SinceCommit" in result

    def test_exits_for_non_git_repo(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            detect_adr_changes(str(tmp_path))
        assert exc_info.value.code == 2

    def test_result_structure(self, git_repo: Path) -> None:
        result = detect_adr_changes(str(git_repo), since_commit="HEAD~1")
        required_keys = [
            "Created", "Modified", "Deleted", "DeletedDetails",
            "HasChanges", "RecommendedAction", "Timestamp", "SinceCommit",
        ]
        for key in required_keys:
            assert key in result


class TestMain:
    """Tests for main entry point."""

    def test_outputs_json(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
        (tmp_path / "README.md").write_text("init")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
        # Add a second commit so HEAD~1 is valid
        (tmp_path / "README.md").write_text("updated")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "update"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )

        with patch("sys.argv", ["detect_adr_changes.py", "--base-path", str(tmp_path)]):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "HasChanges" in data


