"""Tests for the strict review-thread pager in github_core.review_thread_pager.

The pager backs the --all path of resolve_pr_review_thread.py and the thread
read in detect_stale_pr_comments.py. It must page to the end or raise, per
src/claude/rules/lossless-queue-reads.md. No test calls GitHub.
"""

from __future__ import annotations

import pytest

from scripts.github_core.review_thread_pager import (
    ReviewThreadsIncompleteError,
    collect_all_review_threads,
)


def _page(ids: list[str], *, next_cursor: str | None = None, has_next: bool = False) -> dict:
    return {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": has_next, "endCursor": next_cursor},
                    "nodes": [{"id": i, "isResolved": False} for i in ids],
                }
            }
        }
    }


class _Pages:
    """Serve scripted pages and record the cursor each call received."""

    def __init__(self, pages: list[dict | BaseException]) -> None:
        self._pages = list(pages)
        self.cursors: list[str | None] = []

    def __call__(self, cursor: str | None) -> dict:
        self.cursors.append(cursor)
        page = self._pages.pop(0)
        if isinstance(page, BaseException):
            raise page
        return page


class TestCollectAllReviewThreads:
    def test_zero_rows_returns_empty_list(self):
        pages = _Pages([_page([])])

        assert collect_all_review_threads(pages, 7) == []
        assert pages.cursors == [None]

    def test_exactly_one_full_page_reads_once(self):
        ids = [f"t{i}" for i in range(100)]
        pages = _Pages([_page(ids, has_next=False)])

        result = collect_all_review_threads(pages, 7)

        assert [t["id"] for t in result] == ids
        assert len(pages.cursors) == 1

    def test_101_threads_across_two_pages_returns_all(self):
        first = [f"t{i}" for i in range(100)]
        pages = _Pages(
            [
                _page(first, next_cursor="CUR1", has_next=True),
                _page(["t100"], has_next=False),
            ]
        )

        result = collect_all_review_threads(pages, 7)

        assert len(result) == 101
        assert result[-1]["id"] == "t100"
        assert pages.cursors == [None, "CUR1"]

    def test_failure_on_page_two_propagates_not_partial(self):
        pages = _Pages(
            [
                _page(["t0"], next_cursor="CUR1", has_next=True),
                RuntimeError("HTTP 502"),
            ]
        )

        with pytest.raises(RuntimeError, match="HTTP 502"):
            collect_all_review_threads(pages, 7)

    def test_missing_cursor_raises_with_count_read(self):
        pages = _Pages([_page(["t0", "t1"], next_cursor=None, has_next=True)])

        with pytest.raises(ReviewThreadsIncompleteError, match="endCursor empty") as exc:
            collect_all_review_threads(pages, 7)

        assert "read 2 thread(s)" in str(exc.value)

    def test_empty_string_cursor_raises(self):
        pages = _Pages([_page(["t0"], next_cursor="", has_next=True)])

        with pytest.raises(ReviewThreadsIncompleteError, match="endCursor empty"):
            collect_all_review_threads(pages, 7)

    def test_page_cap_raises(self):
        def always_more(cursor: str | None) -> dict:
            return _page(["t"], next_cursor="NEXT", has_next=True)

        with pytest.raises(ReviewThreadsIncompleteError, match="exceeded 3 pages") as exc:
            collect_all_review_threads(always_more, 7, max_pages=3)

        assert "read 3 thread(s)" in str(exc.value)

    @pytest.mark.parametrize(
        "data",
        [
            {},
            {"repository": None},
            {"repository": {"pullRequest": None}},
            {"repository": {"pullRequest": {"reviewThreads": None}}},
            {"repository": {"pullRequest": {"reviewThreads": {"nodes": None}}}},
        ],
        ids=["empty", "no-repo", "no-pr", "no-connection", "null-nodes"],
    )
    def test_missing_connection_raises(self, data):
        with pytest.raises(ReviewThreadsIncompleteError, match="reviewThreads missing"):
            collect_all_review_threads(lambda cursor: data, 7)

    @pytest.mark.parametrize(
        "page_info",
        [
            None,
            {},
            {"endCursor": "CUR1"},
            {"hasNextPage": None},
            {"hasNextPage": "false"},
            {"hasNextPage": 0},
            "not-a-mapping",
        ],
        ids=["null", "empty", "no-flag", "null-flag", "string-flag", "int-flag", "not-mapping"],
    )
    def test_missing_or_invalid_page_info_raises_with_count_read(self, page_info):
        data = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": page_info,
                        "nodes": [{"id": "t0", "isResolved": True}],
                    }
                }
            }
        }

        with pytest.raises(ReviewThreadsIncompleteError, match="hasNextPage") as exc:
            collect_all_review_threads(lambda cursor: data, 7)

        assert "page 1" in str(exc.value)
        assert "read 1 thread(s)" in str(exc.value)

    def test_missing_page_info_without_the_key_raises(self):
        data = {
            "repository": {
                "pullRequest": {"reviewThreads": {"nodes": [{"id": "t0", "isResolved": True}]}}
            }
        }

        with pytest.raises(ReviewThreadsIncompleteError, match="hasNextPage"):
            collect_all_review_threads(lambda cursor: data, 7)

    def test_missing_page_info_on_page_two_reports_progress(self):
        page_two = {
            "repository": {
                "pullRequest": {"reviewThreads": {"nodes": [{"id": "t1", "isResolved": False}]}}
            }
        }
        pages = _Pages([_page(["t0"], next_cursor="CUR1", has_next=True), page_two])

        with pytest.raises(ReviewThreadsIncompleteError, match="page 2") as exc:
            collect_all_review_threads(pages, 7)

        assert "read 2 thread(s)" in str(exc.value)

    def test_missing_connection_on_page_two_reports_progress(self):
        pages = _Pages([_page(["t0"], next_cursor="CUR1", has_next=True), {}])

        with pytest.raises(ReviewThreadsIncompleteError, match="page 2") as exc:
            collect_all_review_threads(pages, 7)

        assert "read 1 thread(s)" in str(exc.value)

    def test_incomplete_error_is_a_runtime_error(self):
        assert issubclass(ReviewThreadsIncompleteError, RuntimeError)
