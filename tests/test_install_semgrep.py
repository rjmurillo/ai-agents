"""Tests for install_semgrep.py subprocess robustness."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.install_semgrep import SUBPROCESS_TIMEOUT_SECONDS, SemgrepInstaller


def test_semgrep_version_check_includes_timeout() -> None:
    with patch("scripts.install_semgrep.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="1.0.0")
        assert SemgrepInstaller().is_installed() is True

    assert run.call_args.kwargs["timeout"] == SUBPROCESS_TIMEOUT_SECONDS


def test_semgrep_install_includes_timeout() -> None:
    with patch("scripts.install_semgrep.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="")
        assert SemgrepInstaller().install() is True

    assert run.call_args.kwargs["timeout"] == SUBPROCESS_TIMEOUT_SECONDS
