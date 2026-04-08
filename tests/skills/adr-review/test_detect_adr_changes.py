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

_get_adr_status = mod._get_adr_status
_get_dependent_adrs = mod._get_dependent_adrs
_run_git = mod._run_git
main = mod.main


class TestGetAdrStatus:
    """Tests for _get_adr_status function."""

    def test_returns_unknown_for_missing_file(self, tmp_path: Path) -> None:
        result = _get_adr_status(tmp_path / "nonexistent.md")
        assert result == "unknown"

    def test_extracts_status_from_frontmatter(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: accepted\n---\n# Title\n")
        result = _get_adr_status(adr)
        assert result == "accepted"

    def test_returns_proposed_when_no_status(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("# ADR-001\nSome content\n")
        result = _get_adr_status(adr)
        assert result == "proposed"

    def test_normalizes_status_to_lowercase(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: DEPRECATED\n---\n")
        result = _get_adr_status(adr)
        assert result == "deprecated"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus:   accepted  \n---\n")
        result = _get_adr_status(adr)
        assert result == "accepted"


class TestGetDependentAdrs:
    """Tests for _get_dependent_adrs function."""

    def test_finds_references(self, tmp_path: Path) -> None:
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001\nReferences ADR-002")
        (arch_dir / "ADR-002.md").write_text("# ADR-002\nNo references")
        # _get_dependent_adrs returns all ADR files containing the search
        # string, including the target ADR itself (ADR-002.md matches "ADR-002").
        result = _get_dependent_adrs("ADR-002", tmp_path)
        assert len(result) == 2
        names = [Path(r).name for r in result]
        assert "ADR-001.md" in names
        assert "ADR-002.md" in names

    def test_returns_empty_for_no_references(self, tmp_path: Path) -> None:
        arch_dir = tmp_path / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001\nNo references")
        result = _get_dependent_adrs("ADR-999", tmp_path)
        assert result == []

    def test_handles_missing_directory(self, tmp_path: Path) -> None:
        result = _get_dependent_adrs("ADR-001", tmp_path)
        assert result == []


class TestRunGit:
    """Tests for _run_git function."""

    def test_returns_completed_process(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        result = _run_git(["status"], cwd=tmp_path)
        assert result.returncode == 0
        assert isinstance(result, subprocess.CompletedProcess)

    def test_returns_error_code_on_failure(self, tmp_path: Path) -> None:
        result = _run_git(["log", "--oneline", "-1"], cwd=tmp_path)
        assert result.returncode != 0

    @patch("subprocess.run", side_effect=FileNotFoundError())
    def test_handles_missing_git(self, mock_run: MagicMock) -> None:
        with pytest.raises(FileNotFoundError):
            _run_git(["status"], cwd=Path("/tmp"))


class TestMain:
    """Tests for main entry point via argparse."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "core.hooksPath", "/dev/null"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
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
        (tmp_path / "README.md").write_text("updated")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "update readme"],
            cwd=str(tmp_path), capture_output=True, check=True,
        )
        return tmp_path

    def test_no_changes(self, git_repo: Path, capsys: pytest.CaptureFixture) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["HasChanges"] is False
        assert data["RecommendedAction"] == "none"

    def test_detects_created_adr(self, git_repo: Path, capsys: pytest.CaptureFixture) -> None:
        arch_dir = git_repo / ".agents" / "architecture"
        arch_dir.mkdir(parents=True)
        (arch_dir / "ADR-001.md").write_text("# ADR-001")
        subprocess.run(["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add ADR"],
            cwd=str(git_repo), capture_output=True, check=True,
        )
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["HasChanges"] is True
        assert len(data["Created"]) == 1
        assert data["RecommendedAction"] == "review"

    def test_result_has_timestamp(self, git_repo: Path, capsys: pytest.CaptureFixture) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "Timestamp" in data
        assert "SinceCommit" in data

    def test_exits_for_non_git_repo(self, tmp_path: Path) -> None:
        exit_code = main(["--base-path", str(tmp_path)])
        assert exit_code == 1

    def test_result_structure(self, git_repo: Path, capsys: pytest.CaptureFixture) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        required_keys = [
            "Created", "Modified", "Deleted", "DeletedDetails",
            "HasChanges", "RecommendedAction", "Timestamp", "SinceCommit",
        ]
        for key in required_keys:
            assert key in data

    def test_outputs_json(self, git_repo: Path, capsys: pytest.CaptureFixture) -> None:
        exit_code = main(["--base-path", str(git_repo)])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "HasChanges" in data
