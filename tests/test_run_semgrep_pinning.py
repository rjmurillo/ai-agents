"""Tests for semgrep version pinning in run_semgrep (issue #4190).

Scope: the pinning helpers _semgrep_pinned_version, _probe_semgrep_version,
and _resolve_semgrep_executable, plus SemgrepScanner._check_semgrep_installed
and run() exit-code contract when the pinned tool is unavailable.

A security scanner that silently falls back to a wrong version reports green.
All pinning failures must exit nonzero and log a clear error.

No real semgrep binary is used; subprocess is mocked throughout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.security.run_semgrep import (
    SemgrepScanner,
    _probe_semgrep_version,
    _resolve_semgrep_executable,
    _semgrep_pinned_version,
    _SemgrepExecutableError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scanner(repo_root: Path) -> SemgrepScanner:
    with patch.object(SemgrepScanner, "_find_repo_root", return_value=repo_root):
        return SemgrepScanner()


def _pyproject(tmp_path: Path, content: str) -> None:
    (tmp_path / "pyproject.toml").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _semgrep_pinned_version
# ---------------------------------------------------------------------------


class TestSemgrepPinnedVersion:
    def test_reads_pin_from_pyproject(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\ndependencies = [\n    "semgrep==1.171.0",\n]\n')
        assert _semgrep_pinned_version(tmp_path) == "1.171.0"

    def test_raises_when_pyproject_missing(self, tmp_path: Path) -> None:
        with pytest.raises(_SemgrepExecutableError, match="cannot read semgrep pin"):
            _semgrep_pinned_version(tmp_path / "nonexistent")

    def test_raises_when_no_pin(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\ndependencies = []\n')
        with pytest.raises(_SemgrepExecutableError, match="must declare exactly one semgrep pin"):
            _semgrep_pinned_version(tmp_path)

    def test_raises_when_ambiguous_pins(self, tmp_path: Path) -> None:
        _pyproject(
            tmp_path,
            '[project]\ndependencies = [\n    "semgrep==1.0.0",\n    "semgrep==2.0.0",\n]\n',
        )
        with pytest.raises(_SemgrepExecutableError, match="must declare exactly one semgrep pin"):
            _semgrep_pinned_version(tmp_path)

    def test_inline_comment_is_not_a_pin(self, tmp_path: Path) -> None:
        """A semgrep version appearing in a comment is not counted as a pin.

        Guards the strict line-anchored regex. If the anchors are removed, a comment like
        ``# was: "semgrep==1.0.0",`` matches the weakened pattern and causes a false pin.
        """
        _pyproject(
            tmp_path,
            '[project]\n# was: "semgrep==1.0.0",\ndependencies = []\n',
        )
        with pytest.raises(_SemgrepExecutableError, match="must declare exactly one semgrep pin"):
            _semgrep_pinned_version(tmp_path)


# ---------------------------------------------------------------------------
# _probe_semgrep_version
# ---------------------------------------------------------------------------


class TestProbeSemgrepVersion:
    def test_returns_version_from_stdout(self) -> None:
        with patch("scripts.security.run_semgrep.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.171.0\n", stderr="")
            assert _probe_semgrep_version("/usr/bin/semgrep") == "1.171.0"

    def test_raises_on_nonzero_exit(self) -> None:
        with patch("scripts.security.run_semgrep.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="broken")
            with pytest.raises(_SemgrepExecutableError, match="version probe exited"):
                _probe_semgrep_version("/usr/bin/semgrep")

    def test_raises_on_empty_output(self) -> None:
        with patch("scripts.security.run_semgrep.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with pytest.raises(_SemgrepExecutableError, match="returned no output"):
                _probe_semgrep_version("/usr/bin/semgrep")

    def test_raises_on_timeout(self) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["semgrep", "--version"], timeout=30),
        ):
            with pytest.raises(_SemgrepExecutableError, match="version probe failed"):
                _probe_semgrep_version("/usr/bin/semgrep")

    def test_raises_on_file_not_found(self) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            side_effect=FileNotFoundError("semgrep"),
        ):
            with pytest.raises(_SemgrepExecutableError, match="version probe failed"):
                _probe_semgrep_version("/usr/bin/semgrep")


# ---------------------------------------------------------------------------
# _resolve_semgrep_executable
# ---------------------------------------------------------------------------


class TestResolveSemgrepExecutable:
    def test_uses_sibling_if_present(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\ndependencies = [\n    "semgrep==1.171.0",\n]\n')
        sibling = tmp_path / "bin" / "semgrep"
        sibling.parent.mkdir(parents=True)
        sibling.write_text("#!/bin/sh\n")
        sibling.chmod(0o755)

        with patch("scripts.security.run_semgrep.sys") as mock_sys:
            mock_sys.executable = str(tmp_path / "bin" / "python")
            result = _resolve_semgrep_executable(tmp_path)

        assert result == str(sibling)

    def test_raises_file_not_found_when_not_on_path(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\ndependencies = [\n    "semgrep==1.171.0",\n]\n')
        with (
            patch("scripts.security.run_semgrep.sys") as mock_sys,
            patch("scripts.security.run_semgrep.shutil.which", return_value=None),
        ):
            mock_sys.executable = str(tmp_path / "bin" / "python")
            with pytest.raises(FileNotFoundError, match="semgrep not found on PATH"):
                _resolve_semgrep_executable(tmp_path)

    def test_raises_version_mismatch(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\ndependencies = [\n    "semgrep==1.171.0",\n]\n')
        with (
            patch("scripts.security.run_semgrep.sys") as mock_sys,
            patch("scripts.security.run_semgrep.shutil.which", return_value="/usr/bin/semgrep"),
            patch("scripts.security.run_semgrep._probe_semgrep_version", return_value="1.0.0"),
        ):
            mock_sys.executable = str(tmp_path / "bin" / "python")
            with pytest.raises(_SemgrepExecutableError, match="version mismatch"):
                _resolve_semgrep_executable(tmp_path)

    def test_returns_path_when_version_matches(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\ndependencies = [\n    "semgrep==1.171.0",\n]\n')
        with (
            patch("scripts.security.run_semgrep.sys") as mock_sys,
            patch("scripts.security.run_semgrep.shutil.which", return_value="/usr/bin/semgrep"),
            patch("scripts.security.run_semgrep._probe_semgrep_version", return_value="1.171.0"),
        ):
            mock_sys.executable = str(tmp_path / "bin" / "python")
            result = _resolve_semgrep_executable(tmp_path)

        assert result == "/usr/bin/semgrep"


# ---------------------------------------------------------------------------
# SemgrepScanner._check_semgrep_installed
# ---------------------------------------------------------------------------


class TestCheckSemgrepInstalled:
    def test_returns_false_when_not_found(self, tmp_path: Path) -> None:
        scanner = _make_scanner(tmp_path)
        with patch(
            "scripts.security.run_semgrep._resolve_semgrep_executable",
            side_effect=FileNotFoundError("semgrep not found on PATH"),
        ):
            assert scanner._check_semgrep_installed() is False

    def test_returns_false_on_version_mismatch(self, tmp_path: Path) -> None:
        scanner = _make_scanner(tmp_path)
        with patch(
            "scripts.security.run_semgrep._resolve_semgrep_executable",
            side_effect=_SemgrepExecutableError("version mismatch: pins 1.0, got 2.0"),
        ):
            assert scanner._check_semgrep_installed() is False

    def test_returns_true_when_resolved(self, tmp_path: Path) -> None:
        scanner = _make_scanner(tmp_path)
        with patch(
            "scripts.security.run_semgrep._resolve_semgrep_executable",
            return_value="/usr/bin/semgrep",
        ):
            assert scanner._check_semgrep_installed() is True


# ---------------------------------------------------------------------------
# SemgrepScanner.run() exit-code contract
# ---------------------------------------------------------------------------


class TestRunExitCode:
    def test_run_exits_2_when_semgrep_missing(self, tmp_path: Path) -> None:
        """run() must return 2 (not 0) when the pinned tool is unavailable."""
        scanner = _make_scanner(tmp_path)
        with patch.object(scanner, "_check_semgrep_installed", return_value=False):
            assert scanner.run() == 2



    def test_run_uses_pinned_executable_in_run_semgrep(self, tmp_path: Path) -> None:
        """_run_semgrep must call the pinned executable, not bare 'semgrep'."""
        scanner = _make_scanner(tmp_path)
        with (
            patch(
                "scripts.security.run_semgrep._resolve_semgrep_executable",
                return_value="/pinned/semgrep",
            ) as mock_resolve,
            patch("scripts.security.run_semgrep.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout='{"results": []}', stderr=""
            )
            scanner._run_semgrep([Path("/repo/a.py")])

        mock_resolve.assert_called_once()
        cmd_arg = mock_run.call_args.args[0]
        assert cmd_arg[0] == "/pinned/semgrep", (
            f"Expected /pinned/semgrep as first cmd arg, got: {cmd_arg[0]!r}"
        )
        assert "semgrep" not in cmd_arg[0].split("/")[-1].replace("semgrep", ""), (
            "Command must use the resolved executable, not PATH lookup"
        )
