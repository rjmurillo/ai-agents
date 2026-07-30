"""Tests for scripts/ci/smoke_install_tarball.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.smoke_install_tarball import main, run, write_github_output


class TestWriteGithubOutput:
    def test_writes_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
            write_github_output("key", "val")
        assert "key=val\n" in out.read_text()

    def test_falls_back_to_stdout_when_not_set(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_OUTPUT", None)
            write_github_output("k", "v")
        assert "k=v" in capsys.readouterr().out


class TestRun:
    def test_missing_tarball_returns_1(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TARBALL", None)
            assert run() == 1

    def test_npm_init_failure_propagates(self, tmp_path: Path) -> None:
        env = {"TARBALL": "/fake/pkg.tgz", "GITHUB_OUTPUT": str(tmp_path / "out.txt")}
        mock_result = MagicMock()
        mock_result.returncode = 2
        with patch.dict(os.environ, env):
            with patch("scripts.ci.smoke_install_tarball.subprocess.run", return_value=mock_result):
                with patch(
                    "scripts.ci.smoke_install_tarball.tempfile.mkdtemp", return_value=str(tmp_path)
                ):
                    assert run() == 2

    def test_npm_install_failure_propagates(self, tmp_path: Path) -> None:
        env = {"TARBALL": "/fake/pkg.tgz", "GITHUB_OUTPUT": str(tmp_path / "out.txt")}
        init_ok = MagicMock(returncode=0)
        install_fail = MagicMock(returncode=3)
        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.smoke_install_tarball.subprocess.run",
                side_effect=[init_ok, install_fail],
            ):
                with patch(
                    "scripts.ci.smoke_install_tarball.tempfile.mkdtemp", return_value=str(tmp_path)
                ):
                    assert run() == 3

    def test_ai_agents_init_failure_propagates(self, tmp_path: Path) -> None:
        env = {"TARBALL": "/fake/pkg.tgz", "GITHUB_OUTPUT": str(tmp_path / "out.txt")}
        ok = MagicMock(returncode=0)
        fail = MagicMock(returncode=5)
        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.smoke_install_tarball.subprocess.run",
                side_effect=[ok, ok, fail],
            ):
                with patch(
                    "scripts.ci.smoke_install_tarball.tempfile.mkdtemp", return_value=str(tmp_path)
                ):
                    assert run() == 5

    def test_success_writes_demo_output(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {"TARBALL": "/fake/pkg.tgz", "GITHUB_OUTPUT": str(out_file)}
        ok = MagicMock(returncode=0)
        with patch.dict(os.environ, env):
            with patch("scripts.ci.smoke_install_tarball.subprocess.run", return_value=ok):
                with patch(
                    "scripts.ci.smoke_install_tarball.tempfile.mkdtemp", return_value=str(tmp_path)
                ):
                    result = run()
        assert result == 0
        assert "demo=" in out_file.read_text()

    def test_npm_commands_called_in_order(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {"TARBALL": "/a/b.tgz", "GITHUB_OUTPUT": str(out_file)}
        ok = MagicMock(returncode=0)
        calls_seen: list[list[str]] = []

        def capture(cmd: list[str], **_kw: object) -> MagicMock:
            calls_seen.append(cmd)
            return ok

        with patch.dict(os.environ, env):
            with patch("scripts.ci.smoke_install_tarball.subprocess.run", side_effect=capture):
                with patch(
                    "scripts.ci.smoke_install_tarball.tempfile.mkdtemp", return_value=str(tmp_path)
                ):
                    run()
        assert calls_seen[0][:2] == ["npm", "init"]
        assert calls_seen[1][:2] == ["npm", "install"]
        assert calls_seen[2][:2] == ["npm", "exec"]


class TestMain:
    def test_main_returns_run_result(self) -> None:
        with patch("scripts.ci.smoke_install_tarball.run", return_value=7):
            assert main() == 7
