"""Tests for scripts/ci/spec_load_content.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_load_content import _gh_issue_body, main, run


class TestGhIssueBody:
    def test_returns_output_on_success(self) -> None:
        mock = MagicMock(returncode=0, stdout="Title\n\nBody text")
        with patch.dict(os.environ, {"GH_TOKEN": "runner-token"}, clear=True):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock):
                result = _gh_issue_body("42", "owner/repo")
        assert "Body text" in result

    def test_returns_empty_on_failure(self) -> None:
        mock = MagicMock(returncode=1, stdout="")
        with patch.dict(os.environ, {"GH_TOKEN": "runner-token"}, clear=True):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock):
                result = _gh_issue_body("999", "owner/repo")
        assert result == ""

    def test_local_issue_uses_runner_token(self) -> None:
        mock = MagicMock(returncode=0, stdout="local content")
        with patch.dict(
            os.environ,
            {"GH_TOKEN": "runner-token", "BOT_PAT": "bot-token"},
            clear=True,
        ):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock) as m:
                _gh_issue_body("5", "owner/repo")
        assert m.call_args.kwargs["env"]["GH_TOKEN"] == "runner-token"

    def test_qualified_same_repo_issue_uses_runner_token(self) -> None:
        mock = MagicMock(returncode=0, stdout="qualified local content")
        with patch.dict(
            os.environ,
            {"GH_TOKEN": "runner-token", "BOT_PAT": "bot-token"},
            clear=True,
        ):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock) as m:
                _gh_issue_body("owner/repo#5", "owner/repo")
        args = m.call_args[0][0]
        assert "repo" in " ".join(args)
        assert "5" in " ".join(args)
        assert m.call_args.kwargs["env"]["GH_TOKEN"] == "runner-token"

    def test_qualified_different_repo_issue_uses_bot_pat(self) -> None:
        mock = MagicMock(returncode=0, stdout="cross-repo content")
        with patch.dict(
            os.environ,
            {"GH_TOKEN": "runner-token", "BOT_PAT": "bot-token"},
            clear=True,
        ):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock) as m:
                _gh_issue_body("owner/other#5", "owner/repo")
        args = m.call_args[0][0]
        assert "other" in " ".join(args)
        assert "5" in " ".join(args)
        assert m.call_args.kwargs["env"]["GH_TOKEN"] == "bot-token"

    def test_cross_repo_issue_requires_bot_pat(self) -> None:
        env = {
            "SPEC_REFS": "",
            "ISSUE_REFS": "owner/other#5",
            "GITHUB_REPOSITORY": "owner/repo",
        }
        with patch.dict(os.environ, env, clear=True):
            assert main() == 2


class TestRun:
    def test_creates_spec_file_output(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("## Spec\nContent")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": str(spec_file),
            "ISSUE_REFS": "",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            rc = run()
        assert rc == 0
        assert "spec_file=" in out_file.read_text()

    def test_loads_spec_by_md_path(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "REQ-001-spec.md"
        spec_file.write_text("# REQ-001")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": str(spec_file),
            "ISSUE_REFS": "",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            run()
        written = (tmp_path / "spec-content-0.md").read_text()
        assert "REQ-001" in written

    def test_loads_issue_body(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": "",
            "ISSUE_REFS": "42",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        mock = MagicMock(returncode=0, stdout="Issue title\n\nIssue body")
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock):
                run()
        written = (tmp_path / "spec-content-0.md").read_text()
        assert "Issue" in written

    def test_fallback_message_when_nothing_found(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": "",
            "ISSUE_REFS": "",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            run()
        written = (tmp_path / "spec-content-0.md").read_text()
        assert "No spec content found" in written


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.spec_load_content.run", return_value=0):
            assert main() == 0
