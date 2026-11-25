"""Tests for GitHub Core module, porting and exceeding Pester coverage."""

from __future__ import annotations

import json
from unittest.mock import patch

from scripts.github_core import get_unresolved_review_threads
from scripts.github_core.api import _retry_after_delay
from tests.github_core_body_guards_cases import (
    TestCapturedTextDecoding,
    TestEscapedNewlineBodyError,
    TestEscapedNewlineGuardIsWiredAtEveryInlineBodySite,
    TestInlineBodyError,
)
from tests.github_core_body_paths_cases import (
    TestAssertValidBodyFile,
    TestAssertValidBodyFileGitDir,
    TestCandidateGitDirRoots,
)
from tests.github_core_body_reading_cases import (
    TestIsAllowedBodyFilePath,
    TestReadBodyFileText,
)
from tests.github_core_comments_cases import (
    Test403PatternMatching,
    TestCreateIssueComment,
    TestGetBotAuthors,
    TestGetBotAuthorsConfig,
    TestGetIssueComments,
    TestGetTrustedSourceComments,
    TestSafeLogStr,
    TestUpdateIssueComment,
)
from tests.github_core_configuration_cases import (
    TestCheckWorkflowRateLimit,
    TestGetPriorityEmoji,
    TestGetReactionEmoji,
    TestIsGhAuthenticated,
    TestParseSimpleYaml,
    TestResolveRepoParams,
    TestYamlFallback,
)
from tests.github_core_graphql_cases import (
    TestCountUnresolvedThreads,
    TestFetchStatus,
    TestFilterUnresolvedThreads,
    TestGhGraphQL,
)
from tests.github_core_repository_cases import (
    TestAssertGhAuthenticated,
    TestGetRepoInfo,
    TestResolveRepoRoot,
)
from tests.github_core_rest_api_cases import (
    TestGetAllPRsWithComments,
    TestGhApiPaginated,
)
from tests.github_core_review_threads_1_cases import _ReviewThreadCases1
from tests.github_core_review_threads_2_cases import _ReviewThreadCases2
from tests.github_core_test_helpers import _completed, _thread
from tests.github_core_validation_cases import (
    TestErrorAndExit,
    TestIsGitHubNameValid,
    TestIsSafeFilePath,
    TestMirrorParity,
    test_thread_mock_keys_subset_of_fixture,
)


class TestGetUnresolvedReviewThreads(_ReviewThreadCases1, _ReviewThreadCases2):
    """Preserve the original collection identity across focused case groups."""

    def test_paginates_until_has_next_page_false(self):
        """Closes PR #1887's pagination cliff: callers see threads on page 2+.

        Two pages: 100 unresolved threads on page 1, 5 unresolved on page 2.
        The PR #1887 retro records that the prior single-page query missed
        the second page entirely and reported "0 unresolved" while threads
        sat there. With pagination, all 105 are returned.
        """
        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "CURSOR_PAGE_2",
                                },
                                "nodes": [_thread(f"page1-{i}", False, i) for i in range(100)],
                            }
                        }
                    }
                }
            }
        )
        page_two = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                                "nodes": [_thread(f"page2-{i}", False, 1000 + i) for i in range(5)],
                            }
                        }
                    }
                }
            }
        )

        responses = [_completed(stdout=page_one), _completed(stdout=page_two)]
        with patch("subprocess.run", side_effect=responses) as mock_run:
            result = get_unresolved_review_threads("owner", "repo", 42)

        assert mock_run.call_count == 2, (
            "Pagination loop did not call gh twice; pageInfo.hasNextPage=true was ignored"
        )
        assert len(result) == 105, (
            f"Expected 105 unresolved threads across pages, got {len(result)}"
        )
        page1_ids = {f"page1-{i}" for i in range(100)}
        page2_ids = {f"page2-{i}" for i in range(5)}
        actual_ids = {t["id"] for t in result}
        assert actual_ids == page1_ids | page2_ids, "Page-2 thread IDs missing from result"

    def test_pagination_passes_cursor_to_second_page(self):
        """The endCursor from page 1 must be sent as $cursor on page 2.

        Without that, GitHub returns page 1 again forever. We assert the
        gh argv on call #2 contains the cursor value from page 1.
        """
        page_one = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "CURSOR_FROM_PAGE_1",
                                },
                                "nodes": [_thread("t1", False, 1)],
                            }
                        }
                    }
                }
            }
        )
        page_two = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [],
                            }
                        }
                    }
                }
            }
        )

        responses = [_completed(stdout=page_one), _completed(stdout=page_two)]
        with patch("subprocess.run", side_effect=responses) as mock_run:
            get_unresolved_review_threads("owner", "repo", 42)

        # Inspect the second subprocess.run call's argv for the cursor value.
        second_call_argv = mock_run.call_args_list[1][0][0]
        joined = " ".join(second_call_argv)
        assert "cursor=CURSOR_FROM_PAGE_1" in joined, (
            f"Cursor from page 1 not propagated to page 2 query; argv was: {joined}"
        )


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


__all__ = [
    "Test403PatternMatching",
    "TestAssertGhAuthenticated",
    "TestAssertValidBodyFile",
    "TestAssertValidBodyFileGitDir",
    "TestCandidateGitDirRoots",
    "TestCapturedTextDecoding",
    "TestCheckWorkflowRateLimit",
    "TestCountUnresolvedThreads",
    "TestCreateIssueComment",
    "TestErrorAndExit",
    "TestEscapedNewlineBodyError",
    "TestEscapedNewlineGuardIsWiredAtEveryInlineBodySite",
    "TestFetchStatus",
    "TestFilterUnresolvedThreads",
    "TestGetAllPRsWithComments",
    "TestGetBotAuthors",
    "TestGetBotAuthorsConfig",
    "TestGetIssueComments",
    "TestGetPriorityEmoji",
    "TestGetReactionEmoji",
    "TestGetRepoInfo",
    "TestGetTrustedSourceComments",
    "TestGetUnresolvedReviewThreads",
    "TestGhApiPaginated",
    "TestGhGraphQL",
    "TestInlineBodyError",
    "TestIsAllowedBodyFilePath",
    "TestIsGhAuthenticated",
    "TestIsGitHubNameValid",
    "TestIsSafeFilePath",
    "TestMirrorParity",
    "TestParseSimpleYaml",
    "TestReadBodyFileText",
    "TestResolveRepoParams",
    "TestResolveRepoRoot",
    "TestRetryAfterDelay",
    "TestSafeLogStr",
    "TestUpdateIssueComment",
    "TestYamlFallback",
    "test_thread_mock_keys_subset_of_fixture",
]
