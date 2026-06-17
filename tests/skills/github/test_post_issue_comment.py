"""Tests for post_issue_comment.py."""

import json
from unittest.mock import patch

import pytest
from github_core.api import RepoInfo
from test_helpers import import_skill_script, make_completed_process


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
        assert result["Success"] is True
        assert result["Data"]["comment_id"] == 100
        assert result["Data"]["skipped"] is False

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
        out = capsys.readouterr().out
        result = json.loads(out.strip().splitlines()[-1])
        assert result["Success"] is True
        assert result["Data"]["skipped"] is True

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
        result = json.loads(out.strip().splitlines()[-1])
        assert result["Success"] is True
        assert result["Data"]["updated"] is True

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

    def test_marker_list_none_stdout_does_not_crash(self, _import_module):
        # Regression for issue #2657: on Windows the comments-list call decoded
        # gh's UTF-8 with cp1252, the stdout reader thread died, and stdout came
        # back None with returncode 0. Feeding None to json.loads crashed with
        # TypeError. The marker path must guard stdout and fall through to
        # posting a new comment. (First mock call = list comments, second = POST.)
        mod = _import_module
        response = {"id": 101, "html_url": "https://example.com/c"}
        with (
            patch("post_issue_comment.assert_gh_authenticated"),
            patch("post_issue_comment.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout=None, returncode=0),
                make_completed_process(stdout=json.dumps(response), returncode=0),
            ]),
        ):
            rc = mod.main(["--issue", "1", "--body", "b", "--marker", "M"])
        assert rc == 0


class TestSubprocessEncoding:
    """Lock the issue #2657 fix: gh subprocess calls must declare UTF-8.

    Bare ``text=True`` decodes with the OS locale codec (cp1252 on Windows),
    which corrupts or drops gh's UTF-8 output. Every gh/git subprocess call in
    the comment path and the shared api helper must pass ``encoding="utf-8"``.
    """

    def test_post_issue_comment_has_no_bare_text_true(self):
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        src = (
            repo_root
            / ".claude/skills/github/scripts/issue/post_issue_comment.py"
        ).read_text(encoding="utf-8")
        assert "text=True" not in src
        assert 'encoding="utf-8"' in src

    def test_github_core_api_has_no_bare_text_true(self):
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        src = (repo_root / ".claude/lib/github_core/api.py").read_text(encoding="utf-8")
        assert "text=True" not in src
        assert 'encoding="utf-8"' in src
