"""Tests for invoke_codeql_scan.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT_DIR = Path(__file__).parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location(
    "invoke_codeql_scan",
    _SCRIPT_DIR / "invoke_codeql_scan.py",
)
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

    def test_invalid_language(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--languages", "java"])


class TestMain:
    @patch("subprocess.run")
    def test_not_in_git_repo(
        self, mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not a repo")
        exit_code = main([])
        assert exit_code == 3
        assert "Not in a git repository" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_validate_config_not_found(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout=str(tmp_path))
        exit_code = main(["--operation", "validate"])
        assert exit_code == 3
        assert "not found" in capsys.readouterr().err

    @patch("subprocess.run")
    def test_validate_success(
        self, mock_run: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config_script = tmp_path / ".codeql" / "scripts" / "Test-CodeQLConfig.ps1"
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
        # Git returns repo root, but no codeql CLI exists
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
        scan_script = tmp_path / ".codeql" / "scripts" / "Invoke-CodeQLScan.ps1"
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
