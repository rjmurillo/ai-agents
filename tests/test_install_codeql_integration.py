"""Tests for install_codeql_integration.py orchestration script."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

_spec = importlib.util.spec_from_file_location(
    "install_codeql_integration",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".codeql",
        "scripts",
        "install_codeql_integration.py",
    ),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

build_parser = _mod.build_parser
get_repo_root = _mod.get_repo_root
step_verify_vscode = _mod.step_verify_vscode
step_verify_pre_commit = _mod.step_verify_pre_commit
main = _mod.main


class TestBuildParser:
    def test_default_values(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.skip_cli is False
        assert args.skip_vscode is False
        assert args.skip_claude_skill is False
        assert args.skip_pre_commit is False
        assert args.ci is False

    def test_skip_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--skip-cli", "--skip-vscode", "--skip-claude-skill", "--skip-pre-commit",
        ])
        assert args.skip_cli is True
        assert args.skip_vscode is True
        assert args.skip_claude_skill is True
        assert args.skip_pre_commit is True


class TestGetRepoRoot:
    def test_returns_path_in_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="/path/to/repo\n",
            )
            result = get_repo_root()
            assert result == "/path/to/repo"

    def test_returns_none_outside_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = get_repo_root()
            assert result is None


class TestStepVerifyVscode:
    def test_all_files_present(self, tmp_path: Path) -> None:
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        (vscode_dir / "extensions.json").write_text("{}")
        (vscode_dir / "tasks.json").write_text("{}")
        (vscode_dir / "settings.json").write_text("{}")

        result = step_verify_vscode(str(tmp_path))
        assert "[PASS]" in result

    def test_missing_files(self, tmp_path: Path) -> None:
        result = step_verify_vscode(str(tmp_path))
        assert "[WARNING]" in result


class TestStepVerifyPreCommit:
    def test_hook_found_with_actionlint(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".githooks"
        hooks_dir.mkdir()
        (hooks_dir / "pre-commit").write_text("#!/bin/sh")

        with patch("shutil.which", return_value="/usr/bin/actionlint"):
            result = step_verify_pre_commit(str(tmp_path))
            assert "[PASS]" in result

    def test_hook_not_found(self, tmp_path: Path) -> None:
        result = step_verify_pre_commit(str(tmp_path))
        assert "[WARNING]" in result


class TestMain:
    def test_not_in_repo_returns_error(self) -> None:
        with patch.object(_mod, "get_repo_root", return_value=None):
            result = main([
                "--skip-cli", "--skip-vscode",
                "--skip-claude-skill", "--skip-pre-commit",
            ])
            assert result == 1

    def test_skip_all_succeeds(self, tmp_path: Path) -> None:
        with (
            patch.object(_mod, "get_repo_root", return_value=str(tmp_path)),
            patch.object(_mod, "step_validate"),
        ):
            result = main([
                "--skip-cli", "--skip-vscode", "--skip-claude-skill",
                "--skip-pre-commit", "--ci",
            ])
            assert result == 0
