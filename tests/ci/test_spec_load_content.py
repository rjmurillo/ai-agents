"""Tests for scripts/ci/spec_load_content.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_load_content import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    _gh_issue_body,
    main,
    run,
)


class TestGhIssueBody:
    def test_returns_output_on_success(self) -> None:
        mock = MagicMock(returncode=0, stdout="Title\n\nBody text")
        with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock):
            exit_code, body = _gh_issue_body("42", "owner/repo")
        assert exit_code == EXIT_OK
        assert "Body text" in body

    def test_returns_external_error_on_failure(self) -> None:
        mock = MagicMock(returncode=1, stdout="", stderr="API unavailable")
        with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock):
            exit_code, body = _gh_issue_body("999", "owner/repo")
        assert exit_code == EXIT_EXTERNAL
        assert body == ""

    def test_parses_cross_repo_ref(self) -> None:
        mock = MagicMock(returncode=0, stdout="cross-repo content")
        with patch("scripts.ci.spec_load_content.subprocess.run", return_value=mock) as m:
            _gh_issue_body("owner/other#5", "owner/repo")
        args = m.call_args[0][0]
        assert "other" in " ".join(args)
        assert "5" in " ".join(args)


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

    def test_no_references_returns_config_error(self, tmp_path: Path) -> None:
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
            assert run() == EXIT_CONFIG
        assert not (tmp_path / "spec-content-0.md").exists()

    def test_loads_spec_id_recursively(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        nested = tmp_path / ".agents" / "specs" / "requirements" / "REQ-005-example.md"
        nested.parent.mkdir(parents=True)
        nested.write_text("# REQ-005\nNested spec", encoding="utf-8")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": "REQ-005",
            "ISSUE_REFS": "",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "5",
        }

        with patch.dict(os.environ, env):
            exit_code = main()

        assert exit_code == EXIT_OK
        written = (tmp_path / "spec-content-5.md").read_text(encoding="utf-8")
        assert "Nested spec" in written

    def test_missing_spec_id_main_returns_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": "REQ-999",
            "ISSUE_REFS": "",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }

        with patch.dict(os.environ, env):
            assert main() == EXIT_CONFIG

    def test_empty_spec_path_main_returns_config(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "empty.md"
        spec_file.write_text(" \n", encoding="utf-8")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": str(spec_file),
            "ISSUE_REFS": "",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }

        with patch.dict(os.environ, env):
            assert main() == EXIT_CONFIG

    def test_empty_recursive_spec_main_returns_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        nested = tmp_path / ".agents" / "specs" / "requirements" / "REQ-005-empty.md"
        nested.parent.mkdir(parents=True)
        nested.write_text("", encoding="utf-8")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": "REQ-005",
            "ISSUE_REFS": "",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }

        with patch.dict(os.environ, env):
            assert main() == EXIT_CONFIG

    def test_issue_lookup_failure_main_returns_external(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_REFS": "",
            "ISSUE_REFS": "42",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
        }
        failure = MagicMock(returncode=1, stdout="", stderr="API unavailable")

        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_load_content.subprocess.run", return_value=failure):
                assert main() == EXIT_EXTERNAL


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.spec_load_content.run", return_value=0):
            assert main() == 0
