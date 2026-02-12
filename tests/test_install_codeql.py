"""Tests for install_codeql.py CodeQL CLI installation script."""

from __future__ import annotations

# Import the module under test by path since it lives in .codeql/scripts/
import importlib.util
import os
import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

_spec = importlib.util.spec_from_file_location(
    "install_codeql",
    os.path.join(
        os.path.dirname(__file__), "..", ".codeql", "scripts", "install_codeql.py",
    ),
)
assert _spec is not None, "Failed to find install_codeql.py"
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None, "Module spec has no loader"
_spec.loader.exec_module(_mod)

build_parser = _mod.build_parser
get_download_url = _mod.get_download_url
check_codeql_installed = _mod.check_codeql_installed
main = _mod.main


class TestBuildParser:
    def test_default_values(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.version == "v2.23.9"
        assert args.install_path == ".codeql/cli"
        assert args.force is False
        assert args.add_to_path is False
        assert args.ci is False

    def test_custom_version(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--version", "v2.24.0"])
        assert args.version == "v2.24.0"

    def test_force_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--force"])
        assert args.force is True

    def test_ci_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci"])
        assert args.ci is True


class TestGetDownloadUrl:
    @patch("platform.system", return_value="Linux")
    def test_linux_url(self, _mock: MagicMock) -> None:
        url = get_download_url("v2.23.9")
        assert "linux64" in url
        assert "v2.23.9" in url

    @patch("platform.system", return_value="Darwin")
    def test_macos_url(self, _mock: MagicMock) -> None:
        url = get_download_url("v2.23.9")
        assert "osx64" in url

    @patch("platform.system", return_value="Windows")
    def test_windows_url(self, _mock: MagicMock) -> None:
        url = get_download_url("v2.23.9")
        assert "win64" in url


class TestCheckCodeQLInstalled:
    def test_not_installed_no_file(self, tmp_path: Path) -> None:
        assert check_codeql_installed(str(tmp_path)) is False

    def test_installed_with_executable(self, tmp_path: Path) -> None:
        exe_name = "codeql.exe" if platform.system().lower() == "windows" else "codeql"
        exe_path = tmp_path / exe_name
        exe_path.write_text("#!/bin/sh\necho test")
        exe_path.chmod(0o755)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = check_codeql_installed(str(tmp_path))
            assert result is True


class TestMain:
    def test_already_installed_no_force(self, tmp_path: Path) -> None:
        with patch.object(_mod, "check_codeql_installed", return_value=True):
            result = main(["--install-path", str(tmp_path), "--ci"])
            assert result == 0

    def test_installation_failure_returns_error(self, tmp_path: Path) -> None:
        install_path = str(tmp_path / "codeql-cli")
        with (
            patch.object(_mod, "check_codeql_installed", return_value=False),
            patch.object(
                _mod,
                "install_codeql_cli",
                side_effect=RuntimeError("download failed"),
            ),
            patch.object(_mod, "get_download_url", return_value="http://example.com"),
        ):
            result = main(["--install-path", install_path, "--ci"])
            assert result == 3
