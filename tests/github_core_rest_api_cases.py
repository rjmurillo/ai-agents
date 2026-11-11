"""Focused GitHub Core contract cases."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from scripts.github_core import get_all_prs_with_comments, gh_api_paginated
from scripts.github_core.api import (
    REST_PAGE_PACE_SECONDS,
    REST_REFUSAL_BACKOFF_SECONDS,
    _retry_after_delay,
)
from tests.github_core_test_helpers import _completed


class TestGhApiPaginated:
    def test_single_page(self):
        items = [{"id": 1}, {"id": 2}]
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(items))):
            result = gh_api_paginated("repos/o/r/issues")
        assert result == items

    def test_multi_page(self):
        page1 = [{"id": i} for i in range(100)]
        page2 = [{"id": 100}]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            data = page1 if call_count == 1 else page2
            return _completed(stdout=json.dumps(data))

        with (
            patch("subprocess.run", side_effect=_side_effect),
            patch("scripts.github_core.api.time.sleep") as sleep,
        ):
            result = gh_api_paginated("repos/o/r/issues", page_size=100)
        assert len(result) == 101
        sleep.assert_called_once_with(REST_PAGE_PACE_SECONDS)

    def test_rate_limit_refusal_retries_page_before_success(self):
        items = [{"id": 1}]
        calls: list[list[str]] = []
        sleeps: list[float] = []

        def _side_effect(command, **kwargs):
            del kwargs
            calls.append(command)
            if len(calls) == 1:
                return _completed(
                    rc=1,
                    stderr="HTTP 403: API rate limit exceeded for user ID 6811113",
                )
            return _completed(stdout=json.dumps(items))

        with (
            patch("subprocess.run", side_effect=_side_effect),
            patch("scripts.github_core.api.time.sleep", sleeps.append),
            pytest.warns(UserWarning, match="GitHub REST page request refused"),
        ):
            result = gh_api_paginated("repos/o/r/issues")

        assert result == items
        assert len(calls) == 2
        assert sleeps == [REST_REFUSAL_BACKOFF_SECONDS[0]]

    def test_empty_response(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")):
            result = gh_api_paginated("repos/o/r/issues")
        assert result == []

    def test_first_page_failure_exits(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="error")):
            with pytest.raises(SystemExit) as exc:
                gh_api_paginated("repos/o/r/issues")
            assert exc.value.code == 3

    def test_mid_pagination_failure_returns_partial(self):
        page1 = [{"id": i} for i in range(100)]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=json.dumps(page1))
            return _completed(rc=1, stderr="rate limited")

        with (
            patch("subprocess.run", side_effect=_side_effect),
            patch("scripts.github_core.api.time.sleep"),
        ):
            with pytest.warns(UserWarning, match="Returning partial results"):
                result = gh_api_paginated("repos/o/r/issues")
        assert len(result) == 100

    def test_invalid_json_first_page_exits(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(SystemExit) as exc:
                gh_api_paginated("repos/o/r/issues")
            assert exc.value.code == 3

    def test_invalid_json_mid_pagination_returns_partial(self):
        page1 = [{"id": i} for i in range(100)]

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=json.dumps(page1))
            return _completed(stdout="not json")

        with (
            patch("subprocess.run", side_effect=_side_effect),
            patch("scripts.github_core.api.time.sleep"),
        ):
            with pytest.warns(UserWarning, match="Invalid JSON"):
                result = gh_api_paginated("repos/o/r/issues")
        assert len(result) == 100

    def test_endpoint_with_query_params_uses_ampersand(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")) as mock:
            gh_api_paginated("repos/o/r/issues?state=open")
        call_args = mock.call_args[0][0]
        assert "&per_page=" in call_args[2]


class TestRetryAfterDelay:
    def test_retry_after_header_overrides_backoff(self):
        """Retry-After: N in error text returns N, not the backoff."""
        delay = _retry_after_delay("gh: rate limited (HTTP 429)\nRetry-After: 42", 2.0)
        assert delay == 42.0

    def test_retry_after_case_insensitive(self):
        """Header matching is case-insensitive."""
        delay = _retry_after_delay("retry-after: 10", 5.0)
        assert delay == 10.0

    def test_no_retry_after_uses_jitter(self):
        """Without Retry-After, the returned delay is in [0, backoff]."""
        backoff = 4.0
        delays = [_retry_after_delay("server error (HTTP 503)", backoff) for _ in range(20)]
        assert all(0.0 <= d <= backoff for d in delays), delays
        # Jitter must not always return the same value (probability of 20 identical
        # draws from uniform(0, 4) is negligible).
        assert len(set(delays)) > 1, "jitter produced identical values - check random source"

    def test_no_retry_after_empty_text(self):
        """Empty error text returns a value in [0, backoff]."""
        delay = _retry_after_delay("", 2.0)
        assert 0.0 <= delay <= 2.0


class TestGetAllPRsWithComments:
    def _make_pr(self, number: int, updated: str, has_comments: bool = True):
        threads = []
        if has_comments:
            threads = [
                {
                    "isResolved": False,
                    "isOutdated": False,
                    "comments": {
                        "nodes": [
                            {
                                "id": "c1",
                                "body": "fix this",
                                "author": {"login": "reviewer"},
                                "createdAt": updated,
                                "path": "file.py",
                            }
                        ]
                    },
                }
            ]
        return {
            "number": number,
            "title": f"PR #{number}",
            "state": "OPEN",
            "author": {"login": "author"},
            "createdAt": updated,
            "updatedAt": updated,
            "mergedAt": None,
            "closedAt": None,
            "reviewThreads": {"nodes": threads},
        }

    def test_returns_prs_with_comments(self):
        pr = self._make_pr(1, "2026-01-15T00:00:00Z")
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [pr],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(result) == 1
        assert result[0]["number"] == 1

    def test_excludes_prs_without_comments(self):
        pr_with = self._make_pr(1, "2026-01-15T00:00:00Z", has_comments=True)
        pr_without = self._make_pr(2, "2026-01-15T00:00:00Z", has_comments=False)
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [pr_with, pr_without],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(result) == 1

    def test_raises_when_repository_is_null(self):
        graphql_response = {"data": {"repository": None}}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            with pytest.raises(RuntimeError, match="not found or not accessible"):
                get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))

    def test_raises_when_pull_requests_is_null(self):
        graphql_response = {"data": {"repository": {"pullRequests": None}}}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            with pytest.raises(RuntimeError, match="Could not retrieve pull requests"):
                get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))

    def test_stops_when_pr_older_than_since(self):
        old_pr = self._make_pr(1, "2025-01-01T00:00:00Z")
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                        "nodes": [old_pr],
                    }
                }
            }
        }

        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(graphql_response))):
            result = get_all_prs_with_comments("owner", "repo", datetime(2026, 1, 1, tzinfo=UTC))
        assert len(result) == 0
