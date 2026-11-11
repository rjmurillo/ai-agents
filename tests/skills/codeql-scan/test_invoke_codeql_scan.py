"""Tests for invoke_codeql_scan.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "codeql-scan" / "scripts"

_spec = importlib.util.spec_from_file_location(
    "invoke_codeql_scan",
    _SCRIPT_DIR / "invoke_codeql_scan.py",
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

main = _mod.main
build_parser = _mod.build_parser
_get_repo_root = _mod._get_repo_root


class TestBuildParser:
    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.operation == "full"
        assert args.languages is None
        assert args.ci is False

    def test_quick_operation(self) -> None:
        args = build_parser().parse_args(["--operation", "quick"])
        assert args.operation == "quick"

    def test_validate_operation(self) -> None:
        args = build_parser().parse_args(["--operation", "validate"])
        assert args.operation == "validate"

    def test_languages(self) -> None:
        args = build_parser().parse_args(["--languages", "python", "actions"])
        assert args.languages == ["python", "actions"]

    def test_ci_mode(self) -> None:
        args = build_parser().parse_args(["--ci"])
        assert args.ci is True

    def test_format_defaults_to_console(self) -> None:
        assert build_parser().parse_args([]).format == "console"

    def test_format_json(self) -> None:
        assert build_parser().parse_args(["--format", "json"]).format == "json"

    def test_invalid_format(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--format", "xml"])

    def test_invalid_language(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--languages", "java"])


class TestGetRepoRoot:
    def test_returns_toplevel_in_git_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n")
            result = _get_repo_root()
            assert result == Path("/repo")
            assert mock_run.call_args.args[0] == [
                "git",
                "rev-parse",
                "--show-toplevel",
            ]

    def test_returns_worktree_top_not_main_checkout(self) -> None:
        """In a linked worktree, repo root is the worktree top (#2373).

        --git-common-dir would have resolved to the main checkout via
        dirname(); --show-toplevel returns this worktree's root verbatim.
        """
        worktree_top = "/repo/.git/worktrees/feat/checkout"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=worktree_top + "\n")
            result = _get_repo_root()
            assert result == Path(worktree_top)

    def test_returns_none_outside_git_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            assert _get_repo_root() is None

    def test_returns_none_on_empty_toplevel(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="\n")
            assert _get_repo_root() is None

    @pytest.mark.parametrize(
        "error",
        [
            FileNotFoundError(2, "No such file or directory: 'git'"),
            PermissionError(13, "Permission denied: 'git'"),
            subprocess.TimeoutExpired(cmd="git", timeout=10),
        ],
        ids=["git-missing", "git-not-executable", "git-hangs"],
    )
    def test_returns_none_when_git_cannot_run(self, error: BaseException) -> None:
        with patch("subprocess.run", side_effect=error):
            assert _get_repo_root() is None

    def test_git_call_is_bounded_by_a_timeout(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n")
            _get_repo_root()
        assert mock_run.call_args.kwargs["timeout"] == _mod.GIT_TIMEOUT_SECONDS


class TestMain:
    @pytest.mark.parametrize("operation", ["full", "quick", "validate"])
    def test_missing_git_is_exit_3_not_a_traceback(
        self, operation: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A missing git binary must not surface as exit 1 ("findings detected")."""
        with patch("subprocess.run", side_effect=FileNotFoundError(2, "git")):
            assert main(["--operation", operation]) == 3
        assert "Not in a git repository" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_not_in_git_repo(self, mock_run: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not a repo")
        exit_code = main([])
        assert exit_code == 3
        assert "Not in a git repository" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_codeql_dir_missing(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--operation", "full"])
        assert exit_code == 0
        assert ".codeql/ not found" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_codeql_dir_missing_default_keeps_stdout_empty(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main([])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    @patch("subprocess.run")
    def test_codeql_dir_missing_json_reports_skipped_with_exit_0(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--operation", "validate", "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert payload["status"] == "skipped"
        assert payload["reason"] == "codeql_directory_missing"
        assert payload["operation"] == "validate"
        assert payload["ci"] is False
        assert payload["exit_code"] == 0

    @patch("subprocess.run")
    def test_codeql_dir_missing_in_ci_exits_2(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--ci"])
        assert exit_code == 2
        assert ".codeql/ not found" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_codeql_dir_missing_in_ci_json_reports_skipped_and_exit_2(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--ci", "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 2
        assert payload["status"] == "skipped"
        assert payload["ci"] is True
        assert payload["exit_code"] == 2

    @patch("subprocess.run")
    def test_codeql_dir_present_in_ci_is_not_skipped(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".codeql").mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--ci", "--operation", "validate", "--format", "json"])
        assert exit_code == 3  # config script missing: a real failure, not a skip
        assert "skipped" not in capsys.readouterr().out

    @patch("subprocess.run")
    def test_validate_config_not_found(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".codeql").mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--operation", "validate"])
        assert exit_code == 3
        assert "not found" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_validate_success(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config_script = tmp_path / ".codeql" / "scripts" / "test_codeql_config.py"
        config_script.parent.mkdir(parents=True)
        config_script.write_text("# config")

        def side_effect(args, **kwargs):
            result = MagicMock()
            if args[0] == "git":
                result.returncode = 0
                result.stdout = str(tmp_path)
            else:
                result.returncode = 0
            return result

        mock_run.side_effect = side_effect
        exit_code = main(["--operation", "validate"])
        assert exit_code == 0

    @patch("subprocess.run")
    def test_codeql_cli_not_found(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Git returns repo root, .codeql/ exists but no CLI binary
        (tmp_path / ".codeql").mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--operation", "full"])
        assert exit_code == 3
        assert "CodeQL CLI not found" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_scan_success(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Set up expected paths
        cli_path = tmp_path / ".codeql" / "cli" / "codeql"
        cli_path.parent.mkdir(parents=True)
        cli_path.write_text("# cli")
        scan_script = tmp_path / ".codeql" / "scripts" / "invoke_codeql_scan.py"
        scan_script.parent.mkdir(parents=True)
        scan_script.write_text("# scan")

        call_count = 0

        def side_effect(args, **kwargs):
            nonlocal call_count
            result = MagicMock()
            if args[0] == "git":
                result.returncode = 0
                result.stdout = str(tmp_path)
            else:
                result.returncode = 0
            call_count += 1
            return result

        mock_run.side_effect = side_effect
        exit_code = main(["--operation", "full"])
        assert exit_code == 0

    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
