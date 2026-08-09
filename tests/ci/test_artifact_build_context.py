"""Tests for scripts/ci/artifact_build_context.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.artifact_build_context import _MAX_LINES_PER_FILE, main, run, write_github_output


class TestWriteGithubOutput:
    def test_writes_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
            write_github_output("m", "n")
        assert "m=n\n" in out.read_text()


class TestRun:
    def test_missing_artifact_file_env_returns_1(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ARTIFACT_FILE", None)
            assert run() == 1

    def test_nonexistent_artifact_file_returns_1(self, tmp_path: Path) -> None:
        env = {"ARTIFACT_FILE": str(tmp_path / "does_not_exist.txt")}
        with patch.dict(os.environ, env):
            assert run() == 1

    def test_empty_artifact_list_returns_0(self, tmp_path: Path) -> None:
        artifact_list = tmp_path / "list.txt"
        artifact_list.write_text("")
        out_file = tmp_path / "out.txt"
        env = {
            "ARTIFACT_FILE": str(artifact_list),
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            assert run() == 0

    def test_context_file_created_with_content(self, tmp_path: Path) -> None:
        # Create a real artifact file and content
        content_file = tmp_path / "session.md"
        content_file.write_text("# Session\nSome content")
        artifact_list = tmp_path / "list.txt"
        artifact_list.write_text(str(content_file) + "\n")
        out_file = tmp_path / "out.txt"
        env = {
            "ARTIFACT_FILE": str(artifact_list),
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            rc = run()
        assert rc == 0
        ctx_file = tmp_path / "artifact-context.md"
        assert ctx_file.exists()
        ctx = ctx_file.read_text()
        assert "## Artifacts to Analyze" in ctx
        assert "Session" in ctx

    def test_truncates_at_max_lines(self, tmp_path: Path) -> None:
        big_file = tmp_path / "big.md"
        # Write 600 lines
        big_file.write_text("\n".join(f"line {i}" for i in range(600)))
        artifact_list = tmp_path / "list.txt"
        artifact_list.write_text(str(big_file) + "\n")
        out_file = tmp_path / "out.txt"
        env = {
            "ARTIFACT_FILE": str(artifact_list),
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            run()
        ctx = (tmp_path / "artifact-context.md").read_text()
        # Zero-indexed lines 0-499 = 500 lines = _MAX_LINES_PER_FILE; line 500 must be absent
        assert f"line {_MAX_LINES_PER_FILE}" not in ctx
        assert "line 0" in ctx

    def test_outputs_context_file_and_size(self, tmp_path: Path) -> None:
        artifact_list = tmp_path / "list.txt"
        artifact_list.write_text("")
        out_file = tmp_path / "out.txt"
        env = {
            "ARTIFACT_FILE": str(artifact_list),
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            run()
        content = out_file.read_text()
        assert "context_file=" in content
        assert "context_size=" in content

    def test_redacts_artifact_credentials_before_context_sink(self, tmp_path: Path) -> None:
        environment_secret = "artifact-environment-secret"
        shaped_secret = f"ghp_{'A' * 36}"
        basic_secret = "dXNlcjpwYXNz"
        token_secret = "arbitrary-value"
        content_file = tmp_path / "session.md"
        content_file.write_text(
            f"env={environment_secret}\nshape={shaped_secret}\n"
            f"Authorization: Basic {basic_secret}\n"
            f"Authorization: Token {token_secret}",
            encoding="utf-8",
        )
        artifact_list = tmp_path / "list.txt"
        artifact_list.write_text(f"{content_file}\n", encoding="utf-8")
        env = {
            "ARTIFACT_FILE": str(artifact_list),
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(tmp_path / "out.txt"),
            "GITHUB_TOKEN": environment_secret,
        }

        with patch.dict(os.environ, env):
            assert run() == 0

        context = (tmp_path / "artifact-context.md").read_text(encoding="utf-8")
        assert environment_secret not in context
        assert shaped_secret not in context
        assert basic_secret not in context
        assert token_secret not in context
        assert "***" in context
        assert "[redacted: github-token]" in context


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.artifact_build_context.run", return_value=0):
            assert main() == 0
