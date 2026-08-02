"""Tests for scripts/ci/artifact_create_issues.py."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.artifact_create_issues import _build_footer, _is_duplicate, main, run


class TestBuildFooter:
    def test_contains_run_url(self) -> None:
        footer = _build_footer("https://github.com", "owner/repo", "123", "session.md")
        assert "owner/repo/actions/runs/123" in footer

    def test_contains_source(self) -> None:
        footer = _build_footer("https://github.com", "owner/repo", "999", "my-file.md")
        assert "my-file.md" in footer


class TestIsDuplicate:
    def test_returns_false_on_gh_failure(self) -> None:
        mock = MagicMock(returncode=1, stdout="")
        with patch("scripts.ci.artifact_create_issues.subprocess.run", return_value=mock):
            assert _is_duplicate("some title") is False

    def test_returns_false_when_no_issues(self) -> None:
        mock = MagicMock(returncode=0, stdout="[]")
        with patch("scripts.ci.artifact_create_issues.subprocess.run", return_value=mock):
            assert _is_duplicate("unique title") is False

    def test_returns_true_on_exact_match(self) -> None:
        issues = json.dumps([{"number": 5, "title": "Bug: broken thing"}])
        mock = MagicMock(returncode=0, stdout=issues)
        with patch("scripts.ci.artifact_create_issues.subprocess.run", return_value=mock):
            assert _is_duplicate("Bug: broken thing") is True

    def test_returns_true_when_title_contains_existing(self) -> None:
        issues = json.dumps([{"number": 7, "title": "broken"}])
        mock = MagicMock(returncode=0, stdout=issues)
        with patch("scripts.ci.artifact_create_issues.subprocess.run", return_value=mock):
            assert _is_duplicate("Bug: broken thing in prod") is True

    def test_returns_false_on_json_error(self) -> None:
        mock = MagicMock(returncode=0, stdout="not json")
        with patch("scripts.ci.artifact_create_issues.subprocess.run", return_value=mock):
            assert _is_duplicate("title") is False


class TestRun:
    def test_missing_findings_json_returns_1(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("FINDINGS_JSON", None)
            assert run() == 1

    def test_malformed_findings_json_returns_1(self) -> None:
        with patch.dict(os.environ, {"FINDINGS_JSON": "not-json"}):
            assert run() == 1

    def test_creates_issue_for_each_finding(self) -> None:
        findings = json.dumps(
            [
                {"title": "Issue A", "body": "Body A", "labels": ["bug"], "source": "file.md"},
                {
                    "title": "Issue B",
                    "body": "Body B",
                    "labels": ["enhancement"],
                    "source": "other.md",
                },
            ]
        )
        env = {
            "FINDINGS_JSON": findings,
            "SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUN_ID": "42",
        }
        ok = MagicMock(returncode=0)
        with patch.dict(os.environ, env):
            with patch("scripts.ci.artifact_create_issues._is_duplicate", return_value=False):
                with patch("scripts.ci.artifact_create_issues.subprocess.run", return_value=ok):
                    rc = run()
        assert rc == 0

    def test_skips_duplicate_finding(self, capsys: pytest.CaptureFixture[str]) -> None:
        findings = json.dumps(
            [
                {"title": "Dup Title", "body": "b", "labels": [], "source": "s.md"},
            ]
        )
        env = {"FINDINGS_JSON": findings}
        with patch.dict(os.environ, env):
            with patch("scripts.ci.artifact_create_issues._is_duplicate", return_value=True):
                rc = run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "Duplicates skipped: 1" in out

    def test_warns_on_gh_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        findings = json.dumps(
            [
                {"title": "New Issue", "body": "b", "labels": [], "source": "s.md"},
            ]
        )
        env = {"FINDINGS_JSON": findings}
        fail = MagicMock(returncode=1)
        with patch.dict(os.environ, env):
            with patch("scripts.ci.artifact_create_issues._is_duplicate", return_value=False):
                with patch("scripts.ci.artifact_create_issues.subprocess.run", return_value=fail):
                    rc = run()
        assert rc == 0  # still 0, just a warning
        assert "::warning::" in capsys.readouterr().out


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.artifact_create_issues.run", return_value=0):
            assert main() == 0
