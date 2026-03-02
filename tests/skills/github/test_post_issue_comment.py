"""Tests for post_issue_comment.py."""

import json
from unittest.mock import patch, MagicMock

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "post_issue_comment"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestEnsureMarkerInBody:
    def test_adds_marker_when_missing(self, _import_module):
        mod = _import_module
        result = mod._ensure_marker_in_body("body", "<!-- M -->")
        assert result == "<!-- M -->\n\nbody"

    def test_keeps_body_when_marker_present(self, _import_module):
        mod = _import_module
        body = "<!-- M -->\n\nbody"
        result = mod._ensure_marker_in_body(body, "<!-- M -->")
        assert result == body


class TestDetectPermissionError:
    def test_detects_403(self, _import_module):
        mod = _import_module
        assert mod._detect_permission_error("HTTP 403 Forbidden") is True
        assert mod._detect_permission_error("status: 403") is True
        assert mod._detect_permission_error("Resource not accessible by integration") is True

    def test_passes_non_403(self, _import_module):
        mod = _import_module
        assert mod._detect_permission_error("HTTP 404 Not Found") is False
        assert mod._detect_permission_error("success") is False


class TestPostIssueComment:
    def test_post_new_comment(self, _import_module):
        mod = _import_module
        response = {"id": 100, "html_url": "https://example.com/comment"}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = make_completed_process(
                stdout=json.dumps(response)
            )
            result = mod.post_issue_comment("o", "r", 1, "hello")

        assert result["Success"] is True
        assert result["CommentId"] == 100
        assert result["Skipped"] is False

    def test_skip_when_marker_exists(self, _import_module):
        mod = _import_module
        comments = [
            {"id": 50, "body": "<!-- TEST-MARKER -->\nold content", "user": {"login": "bot"}},
        ]
        with patch.object(mod, "_find_existing_marker_comment", return_value=comments[0]):
            result = mod.post_issue_comment(
                "o", "r", 1, "new body",
                marker="TEST-MARKER", update_if_exists=False,
            )

        assert result["Success"] is True
        assert result["Skipped"] is True
        assert result["CommentId"] == 50

    def test_update_when_marker_exists_and_update_flag(self, _import_module):
        mod = _import_module
        existing = {"id": 50, "body": "<!-- M -->\nold"}
        updated = {"id": 50, "html_url": "https://url"}
        with (
            patch.object(mod, "_find_existing_marker_comment", return_value=existing),
            patch.object(mod, "_update_comment", return_value=updated),
        ):
            result = mod.post_issue_comment(
                "o", "r", 1, "new body",
                marker="M", update_if_exists=True,
            )

        assert result["Updated"] is True
        assert result["Skipped"] is False

    def test_permission_denied_exits_4(self, _import_module):
        mod = _import_module
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = make_completed_process(
                stderr="HTTP 403 Forbidden", returncode=1,
            )
            with pytest.raises(SystemExit) as exc:
                mod.post_issue_comment("o", "r", 1, "body")

        assert exc.value.code == 4

    def test_api_error_exits_3(self, _import_module):
        mod = _import_module
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = make_completed_process(
                stderr="Internal Server Error", returncode=1,
            )
            with pytest.raises(SystemExit) as exc:
                mod.post_issue_comment("o", "r", 1, "body")

        assert exc.value.code == 3

    def test_json_parse_error_returns_success(self, _import_module):
        mod = _import_module
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = make_completed_process(
                stdout="not json"
            )
            result = mod.post_issue_comment("o", "r", 1, "body")

        assert result["Success"] is True
        assert result["ParseError"] is True
