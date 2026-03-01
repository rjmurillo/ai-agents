"""Tests for install_codeql.py CodeQL CLI installation script."""

from __future__ import annotations

# Import the module under test by path since it lives in .codeql/scripts/
import importlib.util
import os
import platform
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_spec = importlib.util.spec_from_file_location(
    "install_codeql",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".codeql",
        "scripts",
        "install_codeql.py",
    ),
)
assert _spec is not None, "Failed to find install_codeql.py"
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None, "Module spec has no loader"
_spec.loader.exec_module(_mod)

build_parser = _mod.build_parser
get_download_url = _mod.get_download_url
check_codeql_installed = _mod.check_codeql_installed
install_codeql_cli = _mod.install_codeql_cli
add_to_path = _mod.add_to_path
get_default_profile_scripts = _mod.get_default_profile_scripts
CODEQL_MARKER = _mod.CODEQL_MARKER
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


class TestCheckCodeQLInstalledErrorHandling:
    """Tests for specific error logging in check_codeql_installed."""

    def test_corrupted_binary_logs_os_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exe_name = "codeql.exe" if platform.system().lower() == "windows" else "codeql"
        exe_path = tmp_path / exe_name
        exe_path.write_text("corrupted")

        with patch("subprocess.run", side_effect=OSError("Exec format error")):
            result = check_codeql_installed(str(tmp_path))

        assert result is False
        captured = capsys.readouterr()
        assert "not executable" in captured.err
        assert "Exec format error" in captured.err

    def test_timeout_logs_timeout_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exe_name = "codeql.exe" if platform.system().lower() == "windows" else "codeql"
        exe_path = tmp_path / exe_name
        exe_path.write_text("slow binary")

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="codeql version", timeout=30),
        ):
            result = check_codeql_installed(str(tmp_path))

        assert result is False
        captured = capsys.readouterr()
        assert "timed out" in captured.err
        assert "30s" in captured.err

    def test_nonzero_exit_code_logs_stderr(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exe_name = "codeql.exe" if platform.system().lower() == "windows" else "codeql"
        exe_path = tmp_path / exe_name
        exe_path.write_text("bad binary")

        mock_result = MagicMock(returncode=1, stderr="segmentation fault")
        with patch("subprocess.run", return_value=mock_result):
            result = check_codeql_installed(str(tmp_path))

        assert result is False
        captured = capsys.readouterr()
        assert "verification failed" in captured.err
        assert "segmentation fault" in captured.err


class TestAddToPath:
    """Tests for add_to_path function using isolated profile files."""

    def test_creates_new_profile_with_marker(self, tmp_path: Path) -> None:
        profile = tmp_path / ".profile"
        install_path = tmp_path / "codeql-cli"
        install_path.mkdir()

        add_to_path(str(install_path), ci=True, profile_scripts=[profile])

        assert profile.exists()
        content = profile.read_text()
        assert CODEQL_MARKER in content
        assert str(install_path.resolve()) in content

    def test_updates_existing_profile_with_marker(self, tmp_path: Path) -> None:
        profile = tmp_path / ".bashrc"
        profile.write_text("# Existing content\nexport FOO=bar\n")
        install_path = tmp_path / "codeql-cli"
        install_path.mkdir()

        add_to_path(str(install_path), ci=True, profile_scripts=[profile])

        content = profile.read_text()
        assert "# Existing content" in content
        assert CODEQL_MARKER in content
        assert str(install_path.resolve()) in content

    def test_skips_profile_if_marker_exists(self, tmp_path: Path) -> None:
        profile = tmp_path / ".zshrc"
        original_content = f'# Existing\n{CODEQL_MARKER}\nexport PATH="/old/path:$PATH"\n'
        profile.write_text(original_content)
        install_path = tmp_path / "codeql-cli"
        install_path.mkdir()

        add_to_path(str(install_path), ci=True, profile_scripts=[profile])

        content = profile.read_text()
        assert content == original_content
        assert content.count(CODEQL_MARKER) == 1

    def test_multiple_runs_do_not_duplicate_entries(self, tmp_path: Path) -> None:
        profile = tmp_path / ".profile"
        profile.write_text("# Initial profile\n")
        install_path = tmp_path / "codeql-cli"
        install_path.mkdir()

        add_to_path(str(install_path), ci=True, profile_scripts=[profile])
        add_to_path(str(install_path), ci=True, profile_scripts=[profile])
        add_to_path(str(install_path), ci=True, profile_scripts=[profile])

        content = profile.read_text()
        assert content.count(CODEQL_MARKER) == 1

    def test_updates_multiple_profiles(self, tmp_path: Path) -> None:
        bashrc = tmp_path / ".bashrc"
        zshrc = tmp_path / ".zshrc"
        profile = tmp_path / ".profile"

        for p in [bashrc, zshrc, profile]:
            p.write_text(f"# {p.name}\n")

        install_path = tmp_path / "codeql-cli"
        install_path.mkdir()

        add_to_path(
            str(install_path),
            ci=True,
            profile_scripts=[bashrc, zshrc, profile],
        )

        for p in [bashrc, zshrc, profile]:
            content = p.read_text()
            assert CODEQL_MARKER in content
            assert str(install_path.resolve()) in content

    def test_empty_profile_list_skips_file_updates(self, tmp_path: Path) -> None:
        install_path = tmp_path / "codeql-cli"
        install_path.mkdir()
        home_profile = tmp_path / ".profile"

        with patch("pathlib.Path.home", return_value=tmp_path):
            add_to_path(str(install_path), ci=True, profile_scripts=[])

        assert not home_profile.exists()

    def test_handles_permission_error_gracefully(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        profile = tmp_path / ".profile"
        profile.write_text("# Existing\n")
        profile.chmod(0o000)
        install_path = tmp_path / "codeql-cli"
        install_path.mkdir()

        try:
            add_to_path(str(install_path), ci=False, profile_scripts=[profile])

            captured = capsys.readouterr()
            assert "WARNING" in captured.err or "Failed to update" in captured.err
        finally:
            profile.chmod(0o644)


class TestGetDefaultProfileScripts:
    """Tests for get_default_profile_scripts function."""

    def test_returns_bashrc_for_bash_shell(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"SHELL": "/bin/bash"}),
            patch(
                "pathlib.Path.home",
                return_value=tmp_path,
            ),
        ):
            scripts = get_default_profile_scripts()

        assert tmp_path / ".bashrc" in scripts
        assert tmp_path / ".profile" in scripts

    def test_returns_zshrc_for_zsh_shell(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"SHELL": "/bin/zsh"}),
            patch(
                "pathlib.Path.home",
                return_value=tmp_path,
            ),
        ):
            scripts = get_default_profile_scripts()

        assert tmp_path / ".zshrc" in scripts
        assert tmp_path / ".profile" in scripts

    def test_returns_only_profile_for_unknown_shell(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"SHELL": "/bin/sh"}),
            patch(
                "pathlib.Path.home",
                return_value=tmp_path,
            ),
        ):
            scripts = get_default_profile_scripts()

        assert scripts == [tmp_path / ".profile"]


class TestInstallCodeqlCliErrorHandling:
    """Tests for specific exception handling in install_codeql_cli."""

    def test_network_failure_raises_runtime_error(self) -> None:
        with patch(
            "urllib.request.urlretrieve",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with pytest.raises(RuntimeError, match="network error"):
                install_codeql_cli("http://example.com/codeql.tar.gz", "/tmp/codeql", ci=True)

    def test_filesystem_error_raises_runtime_error(self) -> None:
        with patch(
            "urllib.request.urlretrieve",
            side_effect=OSError("No space left on device"),
        ):
            with pytest.raises(RuntimeError, match="filesystem error"):
                install_codeql_cli("http://example.com/codeql.tar.gz", "/tmp/codeql", ci=True)


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
