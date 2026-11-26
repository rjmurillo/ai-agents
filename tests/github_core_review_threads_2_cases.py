"""Review-thread retrieval contract cases."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core import get_unresolved_review_threads
from tests.github_core_test_helpers import _completed, _thread


class _ReviewThreadCases2:
    def test_field_missing_logs_reason_at_api_level(self, caplog):
        """When pullRequest is null, api.py path emits reason=pr_not_found."""
        import logging

        graphql_response = json.dumps({"data": {"repository": {"pullRequest": None}}})
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                return_value=_completed(stdout=graphql_response),
            ):
                result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []
        assert any("reason=pr_not_found" in r.message for r in caplog.records), (
            "Null pullRequest must log reason=pr_not_found at api.py level"
        )

    def test_nodes_missing_logs_reason_at_api_level(self, caplog):
        """reviewThreads.nodes is null (distinct from connection-missing).

        The skill-side has 4 reasons (pr_not_found, field_missing,
        nodes_missing, graphql_error). api.py must emit the same taxonomy
        so operators grepping by reason find both surfaces.
        """
        import logging

        graphql_response = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": None,
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                }
            }
        )
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                return_value=_completed(stdout=graphql_response),
            ):
                result = get_unresolved_review_threads("owner", "repo", 42)
        assert result == []
        assert any("reason=nodes_missing" in r.message for r in caplog.records), (
            "Null reviewThreads.nodes must log reason=nodes_missing"
        )

    def test_cursor_missing_emits_warning_and_logs_reason(self, caplog):
        """When hasNextPage=true but endCursor is empty/null, the loop must
        emit a warnings.warn AND a structured log line with
        ``op=review_threads_failed reason=cursor_missing`` before breaking,
        so callers cannot mistake the partial result for a complete one.
        Defensive guardrail flagged by Copilot review on PR #1897.
        """
        import logging

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
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                side_effect=[_completed(stdout=page_one)],
            ) as mock_run:
                with pytest.warns(UserWarning, match=r"cursor_missing"):
                    result = get_unresolved_review_threads("owner", "repo", 42)
        assert mock_run.call_count == 1
        assert len(result) == 1
        assert any("reason=cursor_missing" in r.message for r in caplog.records), (
            "cursor_missing branch must emit op=review_threads_failed reason=cursor_missing"
        )

    def test_mid_pagination_structural_failure_emits_warning(self, caplog):
        """Page 1 OK, page 2 structurally invalid → caller sees a warning.

        A structurally invalid page-2 response (missing repository.pullRequest
        block, etc.) on a multi-page query truncates the aggregate. Without
        the warning the loop just breaks and callers see N partial threads
        with no signal that pages 2+ were dropped.
        """
        import logging

        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasNextPage": True, "endCursor": "cur1"},
                                "nodes": [_thread("t1", False, 1)],
                            }
                        }
                    }
                }
            }
        )
        page_two_invalid = json.dumps({"data": {"repository": None}})
        with caplog.at_level(logging.WARNING, logger="scripts.github_core.api"):
            with patch(
                "subprocess.run",
                side_effect=[
                    _completed(stdout=page_one),
                    _completed(stdout=page_two_invalid),
                ],
            ):
                with pytest.warns(UserWarning, match=r"structural_failure"):
                    result = get_unresolved_review_threads("owner", "repo", 42)
        assert len(result) == 1, "page 1 result must be preserved on page 2 failure"
        assert any("reason=structural_failure" in r.message for r in caplog.records), (
            "mid-pagination structural failure must emit reason=structural_failure"
        )

    def test_pagination_cap_emits_warning_and_stops(self):
        """At-cap exit must warn the caller, not silently truncate.

        The PR #1887 retro records that a silent first:100 truncation hid 6+
        unresolved threads. A silent at-cap exit at _REVIEW_THREADS_MAX_PAGES
        would reproduce the same false-zero failure mode at the 5000-thread
        boundary. This test asserts: (1) the loop stops at exactly the cap;
        (2) warnings.warn fires with a message naming the cap and the PR;
        (3) the partial result is still returned (not discarded).
        """
        from scripts.github_core.api import _REVIEW_THREADS_MAX_PAGES

        # Every page reports hasNextPage=True and a fresh cursor; one
        # unresolved thread per page so we can count.
        def _page_response(page_idx: int) -> str:
            return json.dumps(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": f"CURSOR_PAGE_{page_idx + 1}",
                                    },
                                    "nodes": [_thread(f"page{page_idx}-t", False, page_idx)],
                                }
                            }
                        }
                    }
                }
            )

        # Provide cap+5 pages. Loop must stop at cap.
        responses = [
            _completed(stdout=_page_response(i)) for i in range(_REVIEW_THREADS_MAX_PAGES + 5)
        ]

        with patch("subprocess.run", side_effect=responses) as mock_run:
            with pytest.warns(UserWarning, match=r"Hit _REVIEW_THREADS_MAX_PAGES"):
                result = get_unresolved_review_threads("owner", "repo", 1894)

        assert mock_run.call_count == _REVIEW_THREADS_MAX_PAGES, (
            f"Loop did not stop at cap; called {mock_run.call_count} times "
            f"(expected {_REVIEW_THREADS_MAX_PAGES})"
        )
        assert len(result) == _REVIEW_THREADS_MAX_PAGES, (
            "Partial threads must be returned alongside the warning, not discarded"
        )
