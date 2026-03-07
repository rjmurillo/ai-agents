"""Tests for post_issue_comment.py."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from test_helpers import import_skill_script
from github_core.api import RepoInfo
from test_helpers import make_completed_process


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def _import_module():
    return import_skill_script("post_issue_comment", "issue")


class TestPrependMarker:
    def test_adds_marker_when_missing(self, _import_module):
        mod = _import_module
        result = mod._prepend_marker("body", "<!-- M -->")
        assert result == "<!-- M -->\n\nbody"

    def test_keeps_body_when_marker_present(self, _import_module):
        mod = _import_module
        body = "<!-- M -->\n\nbody"
        result = mod._prepend_marker(body, "<!-- M -->")
        assert result == body


class TestPermissionDetection:
    """Test that 403 patterns are detected via the _403_PATTERN regex."""

    def test_detects_403(self, _import_module):
        mod = _import_module
        assert mod._403_PATTERN.search("HTTP 403 Forbidden") is not None
        assert mod._403_PATTERN.search("Resource not accessible by integration") is not None

    def test_passes_non_403(self, _import_module):
        mod = _import_module
        assert mod._403_PATTERN.search("HTTP 404 Not Found") is None
        assert mod._403_PATTERN.search("success") is None


class TestPostIssueComment:
    """Tests for post_issue_comment.main."""

    def test_post_new_comment(self, _import_module, capsys):
        mod = _import_module
        response = {"id": 100, "html_url": "https://example.com/comment"}
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(response)
            )),
        ):
            rc = mod.main(["--issue", "1", "--body", "hello"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["comment_id"] == 100
        assert result["skipped"] is False

    def test_skip_when_marker_exists(self, _import_module, capsys):
        mod = _import_module
        marker_html = "<!-- TEST-MARKER -->"
        comments = [{"id": 50, "body": f"{marker_html}\nold content"}]
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(comments)
            )),
        ):
            rc = mod.main([
                "--issue", "1", "--body", "new body",
                "--marker", "TEST-MARKER",
            ])
        assert rc == 0
        # Output has text message then JSON
        out = capsys.readouterr().out
        idx = out.rfind("{")
        result = json.loads(out[idx:])
        assert result["skipped"] is True

    def test_update_when_marker_exists_and_update_flag(self, _import_module, capsys):
        mod = _import_module
        marker_html = "<!-- M -->"
        comments = [{"id": 50, "body": f"{marker_html}\nold"}]
        updated = {"id": 50, "html_url": "https://url", "updated_at": "2024-01-01"}
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(comments)
            )),
            patch("post_issue_comment.update_issue_comment", return_value=updated),
        ):
            rc = mod.main([
                "--issue", "1", "--body", "new body",
                "--marker", "M", "--update-if-exists",
            ])
        assert rc == 0
        out = capsys.readouterr().out
        idx = out.rfind("{")
        result = json.loads(out[idx:])
        assert result["updated"] is True

    def test_permission_denied_exits_4(self, _import_module):
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stderr="HTTP 403 Forbidden", returncode=1,
            )),
            patch("post_issue_comment._save_failed_comment_artifact", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body"])
        assert exc.value.code == 4

    def test_api_error_exits_3(self, _import_module):
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stderr="Internal Server Error", returncode=1,
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--body", "body"])
        assert exc.value.code == 3

    def test_json_parse_error_returns_success(self, _import_module):
        mod = _import_module
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout="not json"
            )),
        ):
            rc = mod.main(["--issue", "1", "--body", "body"])
        assert rc == 0
