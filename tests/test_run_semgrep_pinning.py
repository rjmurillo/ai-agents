"""Tests for semgrep version pinning in run_semgrep (issue #4190).

Scope: the pinning helpers _semgrep_pinned_version, _probe_semgrep_version,
and _resolve_semgrep_executable, plus SemgrepScanner._check_semgrep_installed
and run() exit-code contract when the pinned tool is unavailable.

A security scanner that silently falls back to a wrong version reports green.
All pinning failures must exit nonzero and log a clear error.

No real semgrep binary is used; subprocess is mocked throughout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.security.run_semgrep import (
    _INSTALL_HINT,
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


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts/security/run_semgrep.py"

#: Pin written into the fixture repo. Independent of this repo's real pin so
#: the test does not move when renovate bumps semgrep.
_FIXTURE_PIN = "1.171.0"
#: Version the fake binary reports. Never equal to _FIXTURE_PIN.
_FAKE_VERSION = "9.9.9"

_posix_shim_only = pytest.mark.skipif(
    os.name == "nt",
    reason="the fake semgrep is a POSIX shell shim",
)


def _fixture_repo(tmp_path: Path) -> Path:
    """Create a real git repo carrying a semgrep pin.

    A real repo is required: SemgrepScanner.__init__ resolves the repo root via
    git and raises before any semgrep code runs when the cwd is not a work
    tree, which exits 1 on a traceback and proves nothing about pinning.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    _pyproject(repo, f'[project]\ndependencies = [\n    "semgrep=={_FIXTURE_PIN}",\n]\n')
    return repo


def _fresh_venv_python(tmp_path: Path) -> Path:
    """Create a venv with no semgrep sibling and return its interpreter."""
    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return venv / "bin" / "python"


def _write_fake_semgrep(directory: Path) -> Path:
    """Write an executable semgrep shim that reports _FAKE_VERSION."""
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "semgrep"
    shim.write_text(f"#!/bin/sh\necho {_FAKE_VERSION}\n", encoding="utf-8")
    shim.chmod(0o755)
    return shim


def _run_scanner(
    interpreter: Path,
    repo: Path,
    path_prefix: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the scanner as a process from inside the fixture repo."""
    env = dict(os.environ)
    # The scanner imports scripts.github_core.repo; a bare venv has no
    # editable install of this project, so hand it the source tree.
    env["PYTHONPATH"] = str(_REPO_ROOT)
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [str(interpreter), str(_SCRIPT), "--dry-run"],
        cwd=repo,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )


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
    def test_uses_sibling_when_version_matches(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\ndependencies = [\n    "semgrep==1.171.0",\n]\n')
        sibling = tmp_path / "bin" / "semgrep"
        sibling.parent.mkdir(parents=True)
        sibling.write_text("#!/bin/sh\n")
        sibling.chmod(0o755)

        with (
            patch("scripts.security.run_semgrep.sys") as mock_sys,
            patch(
                "scripts.security.run_semgrep._probe_semgrep_version",
                return_value="1.171.0",
            ),
        ):
            mock_sys.executable = str(tmp_path / "bin" / "python")
            result = _resolve_semgrep_executable(tmp_path)

        assert result == str(sibling)

    def test_raises_when_sibling_version_mismatches(self, tmp_path: Path) -> None:
        """A stale venv sibling must fail, not shortcut the pin check.

        The sibling slot is exactly where a manual `pip install semgrep` or a
        venv left over from an older pin lands. Returning it unverified lets
        the scan pass against a different ruleset than CI runs.
        """
        _pyproject(tmp_path, '[project]\ndependencies = [\n    "semgrep==1.171.0",\n]\n')
        sibling = tmp_path / "bin" / "semgrep"
        sibling.parent.mkdir(parents=True)
        sibling.write_text("#!/bin/sh\n")
        sibling.chmod(0o755)

        with (
            patch("scripts.security.run_semgrep.sys") as mock_sys,
            patch(
                "scripts.security.run_semgrep._probe_semgrep_version",
                return_value="9.9.9",
            ),
            patch("scripts.security.run_semgrep.shutil.which") as mock_which,
        ):
            mock_sys.executable = str(tmp_path / "bin" / "python")
            with pytest.raises(_SemgrepExecutableError, match="version mismatch"):
                _resolve_semgrep_executable(tmp_path)

        assert mock_which.call_count == 0, "a mismatched sibling must not fall back to PATH"

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

    @_posix_shim_only
    def test_run_exits_2_as_subprocess_when_path_semgrep_mismatches(
        self, tmp_path: Path
    ) -> None:
        """A PATH semgrep off the pin exits 2 from a real process.

        Hermetic: a throwaway git repo carrying its own pin, a fresh venv with
        no semgrep sibling, and a fake semgrep first on PATH. Nothing here
        reads the developer's installed semgrep or this repo's pin.
        """
        repo = _fixture_repo(tmp_path)
        interpreter = _fresh_venv_python(tmp_path)
        fake_bin = tmp_path / "fakebin"
        _write_fake_semgrep(fake_bin)

        result = _run_scanner(interpreter, repo, path_prefix=fake_bin)

        assert result.returncode == 2, f"stdout={result.stdout} stderr={result.stderr}"
        assert "version mismatch" in result.stderr
        assert _INSTALL_HINT in result.stderr

    @_posix_shim_only
    def test_run_exits_2_as_subprocess_when_venv_sibling_mismatches(
        self, tmp_path: Path
    ) -> None:
        """A stale venv sibling exits 2 instead of reporting a clean pass.

        Discriminating input: with the sibling returned unverified, the scan
        gets past the install check, finds no tracked files in the fixture
        repo, logs "PASS: No files to scan" and exits 0. The wrong semgrep
        reads as green.
        """
        repo = _fixture_repo(tmp_path)
        interpreter = _fresh_venv_python(tmp_path)
        _write_fake_semgrep(interpreter.parent)

        result = _run_scanner(interpreter, repo)

        assert result.returncode == 2, f"stdout={result.stdout} stderr={result.stderr}"
        assert "version mismatch" in result.stderr

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
