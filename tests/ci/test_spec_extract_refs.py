"""Tests for scripts/ci/spec_extract_refs.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_extract_refs import (
    _extract_incremental_scope,
    _extract_issue_refs,
    _extract_spec_refs,
    main,
    run,
)


class TestExtractSpecRefs:
    def test_extracts_req_ids(self) -> None:
        result = _extract_spec_refs("See REQ-001 and REQ-042 for details")
        assert "REQ-001" in result
        assert "REQ-042" in result

    def test_extracts_design_ids(self) -> None:
        result = _extract_spec_refs("Implements DESIGN-007")
        assert "DESIGN-007" in result

    def test_extracts_task_ids(self) -> None:
        result = _extract_spec_refs("Closes TASK-123")
        assert "TASK-123" in result

    def test_extracts_spec_file_paths(self) -> None:
        result = _extract_spec_refs("See .agents/specs/my-spec.md for details")
        assert ".agents/specs/my-spec.md" in result

    def test_extracts_planning_paths(self) -> None:
        result = _extract_spec_refs("Plan: .agents/planning/sprint.md")
        assert ".agents/planning/sprint.md" in result

    def test_empty_string_returns_empty(self) -> None:
        assert _extract_spec_refs("no references here") == ""

    def test_deduplicates(self) -> None:
        refs = _extract_spec_refs("REQ-001 REQ-001 REQ-002")
        parts = refs.split()
        assert parts.count("REQ-001") == 1


class TestExtractIssueRefs:
    def test_extracts_fixes_ref(self) -> None:
        result = _extract_issue_refs("Fixes #42")
        assert "42" in result

    def test_extracts_closes_ref(self) -> None:
        result = _extract_issue_refs("Closes #100")
        assert "100" in result

    def test_extracts_cross_repo_ref(self) -> None:
        result = _extract_issue_refs("Implements owner/repo#55")
        assert "owner/repo#55" in result

    def test_no_refs_returns_empty(self) -> None:
        assert _extract_issue_refs("no references") == ""

    def test_deduplicates(self) -> None:
        result = _extract_issue_refs("Fixes #5 Fixes #5")
        parts = result.split()
        assert parts.count("5") == 1


class TestExtractIncrementalScope:
    def test_returns_stdout_on_success(self) -> None:
        mock = MagicMock(returncode=0, stdout="phase-1\n")
        with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=mock):
            assert _extract_incremental_scope("feat: phase-1 impl") == "phase-1"

    def test_returns_empty_on_failure(self) -> None:
        mock = MagicMock(returncode=1, stdout="")
        with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=mock):
            assert _extract_incremental_scope("feat: unknown") == ""


class TestRun:
    def test_has_specs_false_when_no_refs(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "chore: bump version",
            "PR_BODY_INPUT": "No spec here.",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_extract_refs.subprocess.run",
                return_value=MagicMock(returncode=0, stdout=""),
            ):
                rc = run()
        assert rc == 0
        assert "has_specs=false" in out_file.read_text()

    def test_has_specs_true_when_refs_found(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "feat: implement REQ-001",
            "PR_BODY_INPUT": "Fixes #10",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_extract_refs.subprocess.run",
                return_value=MagicMock(returncode=0, stdout=""),
            ):
                run()
        assert "has_specs=true" in out_file.read_text()

    def test_fallback_to_gh_when_no_inputs(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "PR_TITLE_INPUT": "",
            "PR_BODY_INPUT": "",
            "PR_NUMBER": "7",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(out_file),
            "GITHUB_RUN_ID": "0",
        }
        gh_mock = MagicMock(returncode=0, stdout="title text")
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_extract_refs.subprocess.run", return_value=gh_mock):
                rc = run()
        assert rc == 0


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.spec_extract_refs.run", return_value=0):
            assert main() == 0
