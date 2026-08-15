"""Tests for PR #5011 review thread fixes.

Covers:
1. GraphQL response shape validation (list, null, non-dict errors items)
2. Permission denial (Resource not accessible by integration) exit 4,
   while keeping rate-limit 403s as exit 3
3. Commit probe body validation on exit 0
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import _parse_graphql_response, is_auth_failure_text

# ---------------------------------------------------------------------------
# 1. GraphQL response shape validation (_parse_graphql_response)
# ---------------------------------------------------------------------------


class TestParseGraphqlResponseShapeValidation:
    """Thread PRRT_kwDOQoWRls6ZcLU-: validate decoded shapes before .get()."""

    def test_list_response_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="not a JSON object"):
            _parse_graphql_response("[]")

    def test_null_response_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="not a JSON object"):
            _parse_graphql_response("null")

    def test_string_response_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="not a JSON object"):
            _parse_graphql_response('"just a string"')

    def test_integer_response_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="not a JSON object"):
            _parse_graphql_response("42")

    def test_errors_list_with_string_items(self):
        """{"errors":["bad"]} should not raise AttributeError."""
        payload = json.dumps({"errors": ["bad gateway"]})
        with pytest.raises(RuntimeError, match="GraphQL errors.*bad gateway"):
            _parse_graphql_response(payload)

    def test_errors_not_a_list_raises(self):
        payload = json.dumps({"errors": "single string"})
        with pytest.raises(RuntimeError, match="not a list"):
            _parse_graphql_response(payload)

    def test_errors_with_dict_items_extracts_message(self):
        payload = json.dumps({"errors": [{"message": "rate limited"}]})
        with pytest.raises(RuntimeError, match="rate limited"):
            _parse_graphql_response(payload)

    def test_valid_response_returns_data(self):
        payload = json.dumps(
            {"data": {"repository": {"pullRequest": {"merged": True}}}}
        )
        result = _parse_graphql_response(payload)
        assert result == {"repository": {"pullRequest": {"merged": True}}}

    def test_valid_response_no_data_returns_empty_dict(self):
        payload = json.dumps({"something": "else"})
        result = _parse_graphql_response(payload)
        assert result == {}


# ---------------------------------------------------------------------------
# 2. Permission denial vs rate-limit 403 (is_auth_failure_text)
# ---------------------------------------------------------------------------


class TestPermissionDenialExitCode:
    """Thread PRRT_kwDOQoWRls6ZcLVQ: Resource not accessible -> exit 4."""

    def test_resource_not_accessible_is_auth_failure(self):
        text = "gh: Resource not accessible by integration (HTTP 403)"
        assert is_auth_failure_text(text) is True

    def test_resource_not_accessible_case_insensitive(self):
        text = "resource not accessible by integration"
        assert is_auth_failure_text(text) is True

    def test_rate_limit_403_is_not_auth_failure(self):
        text = "gh: rate limit exceeded (HTTP 403)"
        assert is_auth_failure_text(text) is False

    def test_secondary_rate_limit_403_is_not_auth_failure(self):
        text = (
            "gh: secondary rate limit; "
            "Resource not accessible by integration"
        )
        assert is_auth_failure_text(text) is False

    def test_abuse_detection_not_auth_failure(self):
        text = (
            "abuse detection; "
            "Resource not accessible by integration"
        )
        assert is_auth_failure_text(text) is False

    def test_plain_403_without_permission_marker_not_auth(self):
        text = "gh: forbidden (HTTP 403)"
        assert is_auth_failure_text(text) is False

    def test_credential_markers_still_work(self):
        assert is_auth_failure_text("Bad credentials") is True
        assert is_auth_failure_text("not logged in") is True
        assert is_auth_failure_text("requires authentication") is True


# ---------------------------------------------------------------------------
# 3. Commit probe body validation on exit 0 (close_issue.py)
# ---------------------------------------------------------------------------

# Import close_issue lazily to avoid module identity conflicts with
# test_close_issue.py which also registers sys.modules["close_issue"].

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _get_close_mod():
    if "close_issue" in sys.modules:
        return sys.modules["close_issue"]
    spec = importlib.util.spec_from_file_location(
        "close_issue", _SCRIPTS_DIR / "close_issue.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["close_issue"] = mod
    spec.loader.exec_module(mod)
    return mod


def _completed(stdout="", stderr="", rc=0):
    return subprocess.CompletedProcess(
        args=[], returncode=rc, stdout=stdout, stderr=stderr
    )


class TestCommitProbeBodyValidation:
    """Thread PRRT_kwDOQoWRls6ZcRCI: validate response body on exit 0."""

    def test_valid_sha_passes(self):
        response = _completed(stdout='{"sha":"abc1234def5678"}', rc=0)
        with patch("subprocess.run", return_value=response):
            result = _get_close_mod().verify_claims(
                _get_close_mod().Claims(commits=("abc1234",), prs=()),
                owner="o", repo="r",
            )
        assert result.blocked is False

    def test_empty_body_exits_3(self):
        response = _completed(stdout="", rc=0)
        with patch("subprocess.run", return_value=response):
            result = _get_close_mod().verify_claims(
                _get_close_mod().Claims(commits=("abc1234",), prs=()),
                owner="o", repo="r",
            )
        assert result.exit_code == 3
        err = result.probe_errors[0].lower()
        assert "sha" in err

    def test_non_json_body_exits_3(self):
        response = _completed(stdout="<html>Bad Gateway</html>", rc=0)
        with patch("subprocess.run", return_value=response):
            result = _get_close_mod().verify_claims(
                _get_close_mod().Claims(commits=("abc1234",), prs=()),
                owner="o", repo="r",
            )
        assert result.exit_code == 3

    def test_json_array_body_exits_3(self):
        response = _completed(stdout="[]", rc=0)
        with patch("subprocess.run", return_value=response):
            result = _get_close_mod().verify_claims(
                _get_close_mod().Claims(commits=("abc1234",), prs=()),
                owner="o", repo="r",
            )
        assert result.exit_code == 3

    def test_json_no_sha_field_exits_3(self):
        response = _completed(stdout='{"commit":{"message":"hi"}}', rc=0)
        with patch("subprocess.run", return_value=response):
            result = _get_close_mod().verify_claims(
                _get_close_mod().Claims(commits=("abc1234",), prs=()),
                owner="o", repo="r",
            )
        assert result.exit_code == 3

    def test_sha_mismatch_exits_3(self):
        response = _completed(stdout='{"sha":"ffffffff"}', rc=0)
        with patch("subprocess.run", return_value=response):
            result = _get_close_mod().verify_claims(
                _get_close_mod().Claims(commits=("abc1234",), prs=()),
                owner="o", repo="r",
            )
        assert result.exit_code == 3
        assert "does not match" in result.probe_errors[0]
