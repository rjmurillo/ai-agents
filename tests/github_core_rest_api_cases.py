"""Focused GitHub Core contract cases."""

from __future__ import annotations

import json
import warnings
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from scripts.github_core import get_all_prs_with_comments, gh_api_paginated
from scripts.github_core.api import (
    REST_PAGE_PACE_SECONDS,
    REST_REFUSAL_BACKOFF_SECONDS,
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

    def test_mid_pagination_failure_exits_3_not_partial(self, capsys):
        page1 = [{"id": i} for i in range(100)]
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=json.dumps(page1))
            return _completed(rc=1, stderr="HTTP 502: bad gateway")

        with (
            patch("subprocess.run", side_effect=_side_effect),
            patch("scripts.github_core.api.time.sleep"),
            pytest.raises(SystemExit) as exc,
        ):
            gh_api_paginated("repos/o/r/issues")

        assert exc.value.code == 3
        err = capsys.readouterr().err
        assert "page 2" in err
        assert "100 items read" in err

    def test_invalid_json_first_page_exits(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(SystemExit) as exc:
                gh_api_paginated("repos/o/r/issues")
            assert exc.value.code == 3

    def test_invalid_json_mid_pagination_exits_3_not_partial(self, capsys):
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
            pytest.raises(SystemExit) as exc,
        ):
            gh_api_paginated("repos/o/r/issues")

        assert exc.value.code == 3
        assert "Invalid JSON" in capsys.readouterr().err

    def test_endpoint_with_query_params_uses_ampersand(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")) as mock:
            gh_api_paginated("repos/o/r/issues?state=open")
        call_args = mock.call_args[0][0]
        assert "&per_page=" in call_args[2]

    def test_exactly_one_full_page_then_empty_page_returns_all(self):
        page1 = [{"id": i} for i in range(100)]
        responses = iter([json.dumps(page1), "[]"])

        with (
            patch(
                "subprocess.run",
                side_effect=lambda *a, **k: _completed(stdout=next(responses)),
            ),
            patch("scripts.github_core.api.time.sleep"),
        ):
            result = gh_api_paginated("repos/o/r/issues", page_size=100)

        assert result == page1


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

    def _page(self, has_next: bool, cursor: str | None):
        pr = self._make_pr(1, "2026-01-15T00:00:00Z")
        return {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                        "nodes": [pr],
                    }
                }
            }
        }

    def test_raises_when_page_cap_hit_with_pages_left(self):
        always_more = _completed(stdout=json.dumps(self._page(True, "next")))

        with patch("subprocess.run", return_value=always_more) as run:
            with pytest.raises(RuntimeError, match="Pagination exceeded 2 pages"):
                get_all_prs_with_comments(
                    "owner", "repo", datetime(2026, 1, 1, tzinfo=UTC), max_pages=2
                )

        assert run.call_count == 2

    def test_last_page_landing_on_cap_returns_without_warning(self):
        pages = [
            _completed(stdout=json.dumps(self._page(True, "c1"))),
            _completed(stdout=json.dumps(self._page(False, None))),
        ]

        with patch("subprocess.run", side_effect=pages), warnings.catch_warnings():
            warnings.simplefilter("error")
            result = get_all_prs_with_comments(
                "owner", "repo", datetime(2026, 1, 1, tzinfo=UTC), max_pages=2
            )

        assert len(result) == 2
