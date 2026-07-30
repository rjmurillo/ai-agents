"""Tests for scripts/ci/artifact_collect.py."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.artifact_collect import collect_artifacts, main, run, write_github_output


class TestWriteGithubOutput:
    def test_writes_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
            write_github_output("k", "v")
        assert "k=v\n" in out.read_text()

    def test_stdout_fallback(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_OUTPUT", None)
            write_github_output("x", "y")
        assert "x=y" in capsys.readouterr().out


class TestCollectArtifacts:
    def test_returns_empty_when_no_dirs_exist(self, tmp_path: Path) -> None:
        with patch("scripts.ci.artifact_collect.Path") as mock_path_cls:
            # Fake all directories as non-existent
            mock_base = mock_path_cls.return_value
            mock_base.is_dir.return_value = False
            # Actually call original Path for the function
        # Use monkeypatch via tmp_path CWD
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = collect_artifacts(7)
        finally:
            os.chdir(original_cwd)
        assert result == []

    def test_returns_recent_files(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        recent = sessions / "recent.md"
        recent.write_text("x")
        # mtime is already "now", within 7 days
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = collect_artifacts(7)
        finally:
            os.chdir(original_cwd)
        assert str(recent.relative_to(tmp_path)) in result

    def test_excludes_old_files(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        old = sessions / "old.md"
        old.write_text("x")
        # Force mtime to 30 days ago
        old_time = time.time() - 30 * 86400
        os.utime(old, (old_time, old_time))
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = collect_artifacts(7)
        finally:
            os.chdir(original_cwd)
        assert not result


class TestRun:
    def test_zero_artifacts_still_succeeds(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "SCAN_DEPTH_DAYS": "7",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                rc = run()
        finally:
            os.chdir(original_cwd)
        assert rc == 0
        assert "artifact_count=0" in out_file.read_text()

    def test_writes_artifact_file_path_to_output(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                run()
        finally:
            os.chdir(original_cwd)
        assert "artifact_file=" in out_file.read_text()

    def test_notice_printed_when_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                run()
        finally:
            os.chdir(original_cwd)
        assert "::notice::" in capsys.readouterr().out


class TestMain:
    def test_main_delegates_to_run(self) -> None:
        with patch("scripts.ci.artifact_collect.run", return_value=0):
            assert main() == 0
