"""Review-thread retrieval contract cases."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core import get_unresolved_review_threads
from tests.github_core_test_helpers import _completed, _thread


class _ReviewThreadCases1:
    def test_returns_unresolved_threads(self):
        graphql_response = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    _thread("t1", False, 1),
                                    _thread("t2", True, 2),
                                    _thread("t3", False, 3),
                                ]
                            }
                        }
                    }
                }
            }
        )
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert len(result) == 2
        assert all(not t["isResolved"] for t in result)

    def test_returns_empty_on_all_resolved(self):
        graphql_response = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    _thread("t1", True, 1),
                                ]
                            }
                        }
                    }
                }
            }
        )
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_returns_empty_on_no_threads(self):
        graphql_response = json.dumps(
            {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": []}}}}}
        )
        with patch("subprocess.run", return_value=_completed(stdout=graphql_response)):
            result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_returns_empty_on_api_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="network error")):
            with pytest.warns(UserWarning, match="Failed to query review threads.*network error"):
                result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []

    def test_never_returns_none(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="fail")):
            with pytest.warns(UserWarning):
                result = get_unresolved_review_threads("owner", "repo", 1)
        assert result is not None
        assert isinstance(result, list)

    def test_pagination_stops_when_endcursor_is_empty(self):
        """Defensive: a hasNextPage=true with empty endCursor must not loop forever."""
        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasNextPage": True, "endCursor": ""},
                                "nodes": [_thread("t1", False, 1)],
                            }
                        }
                    }
                }
            }
        )

        with (
            patch("subprocess.run", side_effect=[_completed(stdout=page_one)]) as mock_run,
            pytest.warns(UserWarning, match="Reason: cursor_missing"),
        ):
            result = get_unresolved_review_threads("owner", "repo", 42)

        assert mock_run.call_count == 1, "Loop did not stop on empty endCursor"
        assert len(result) == 1

    def test_graphql_error_logs_reason_at_api_level(self, caplog):
        """The api.py-level _fetch_review_threads_page logs reason=graphql_error
        with op=review_threads_failed, distinct from the script-level logger.
        Without this, an operator grepping api.py logs for the failure reason
        would not see why a transport error occurred.
        """
        import logging

        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                return_value=_completed(rc=1, stderr="rate limit"),
            ):
                with pytest.warns(UserWarning):
                    result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []
        assert any(
            "op=review_threads_failed" in r.message and "reason=graphql_error" in r.message
            for r in caplog.records
        ), "api.py-level transport error must log op=review_threads_failed reason=graphql_error"
