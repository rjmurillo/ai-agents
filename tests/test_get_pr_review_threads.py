"""Tests for get_pr_review_threads.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.mock_fidelity import assert_mock_keys_match

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_pr_review_threads")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _envelope(capsys) -> dict:
    """Parse the captured stdout into the ADR-056 envelope dict.

    The script emits the {Success, Data, Error, Metadata} envelope as JSON when
    stdout is not a TTY (pytest's capsys redirect satisfies that). Tests assert
    on the envelope and on its Data payload.
    """
    return json.loads(capsys.readouterr().out)


def _data(capsys) -> dict:
    """Return just the Data payload of the captured envelope."""
    return _envelope(capsys)["Data"]


def _graphql_response(threads=None, total_count=None):
    if threads is None:
        threads = []
    if total_count is None:
        total_count = len(threads)
    return json.dumps({
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "totalCount": total_count,
                        "nodes": threads,
                    },
                },
            },
        },
    })


def _thread(thread_id="PRRT_1", resolved=False, outdated=False, path="file.py",
            line=10, body="comment", author="alice"):
    return {
        "id": thread_id,
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": path,
        "line": line,
        "startLine": None,
        "diffSide": "RIGHT",
        "comments": {
            "totalCount": 1,
            "nodes": [
                {
                    "id": "C1",
                    "databaseId": 100,
                    "body": body,
                    "author": {"login": author},
                    "createdAt": "2025-01-01T00:00:00Z",
                    "updatedAt": "2025-01-01T00:00:00Z",
                },
            ],
        },
    }


def test_mock_thread_shape_matches_fixture():
    """Validate that the thread mock shape matches the canonical fixture."""
    thread = _thread()
    assert_mock_keys_match(thread, "review_thread", allow_extra=True)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_flags(self):
        args = build_parser().parse_args([
            "--pull-request", "50", "--unresolved-only", "--include-comments",
        ])
        assert args.unresolved_only is True
        assert args.include_comments is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="Could not resolve"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_success_all_threads(self, capsys):
        threads = [_thread("PRRT_1", resolved=False), _thread("PRRT_2", resolved=True)]
        response = _graphql_response(threads)
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = _data(capsys)
        assert isinstance(output, dict)
        assert isinstance(output["total_threads"], int)
        assert output["total_threads"] == 2
        assert isinstance(output["unresolved_count"], int)
        assert output["unresolved_count"] == 1
        assert isinstance(output["resolved_count"], int)
        assert output["resolved_count"] == 1
        assert isinstance(output["threads"], list)

    def test_unresolved_only_filter(self, capsys):
        threads = [_thread("PRRT_1", resolved=False), _thread("PRRT_2", resolved=True)]
        response = _graphql_response(threads)
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50", "--unresolved-only"])
        assert rc == 0
        output = _data(capsys)
        assert len(output["threads"]) == 1
        assert output["threads"][0]["is_resolved"] is False

    def test_include_comments(self, capsys):
        threads = [_thread("PRRT_1")]
        response = _graphql_response(threads)
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50", "--include-comments"])
        assert rc == 0
        output = _data(capsys)
        assert output["threads"][0]["comments"] is not None
        assert len(output["threads"][0]["comments"]) == 1

    def test_empty_threads(self, capsys):
        response = _graphql_response([])
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = _data(capsys)
        assert output["total_threads"] == 0

    def test_output_uses_standard_envelope(self, capsys):
        """Contract: output is the ADR-056 envelope, not a flat lowercase dict.

        Issue #2372: consumers reading `.Data` per the GitHub skill docs got
        null because the script printed flat keys (success, threads, ...) at the
        top level. This pins the {Success, Data, Error, Metadata} shape and that
        the documented Data payload fields are all present and reachable.
        """
        threads = [_thread("PRRT_1", resolved=False), _thread("PRRT_2", resolved=True)]
        response = _graphql_response(threads)
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0

        envelope = _envelope(capsys)
        assert set(envelope) == {"Success", "Data", "Error", "Metadata"}
        assert envelope["Success"] is True
        assert envelope["Error"] is None
        assert envelope["Metadata"]["Script"] == "get_pr_review_threads.py"
        assert "Version" in envelope["Metadata"]
        assert "Timestamp" in envelope["Metadata"]

        # No flat lowercase keys leak at the top level (the #2372 regression).
        assert "success" not in envelope
        assert "threads" not in envelope

        data = envelope["Data"]
        for key in (
            "pull_request",
            "owner",
            "repo",
            "total_threads",
            "resolved_count",
            "unresolved_count",
            "pagination_truncated",
            "threads",
        ):
            assert key in data, f"Data missing documented field: {key}"
        assert data["threads"] is not None

    def test_api_error_exits_3(self):
        """Generic RuntimeError (not 'Could not resolve') exits with code 3."""
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_threads._run_threads_query",
            side_effect=RuntimeError("rate limit exceeded"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

    def test_threads_none_exits_2(self):
        """PR found but reviewThreads nodes is None exits with code 2."""
        data = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {"nodes": None, "totalCount": 0},
                },
            },
        }
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_threads._run_threads_query",
            return_value=data,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 2

    def test_missing_pull_request_exits_2(self):
        """Missing pullRequest in response exits with code 2."""
        data = {"repository": {}}
        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_threads._run_threads_query",
            return_value=data,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 2

    def test_paginates_across_multiple_pages(self, capsys):
        """The PR #1887 cliff: a >100-thread PR must report all threads, not page 1.

        Two pages mocked at the GraphQL layer; the script's main() should
        return the union of both pages in `threads` and report the right
        totals in `total_threads` / `unresolved_count`.
        """
        page1_threads = [_thread(f"p1-{i}", resolved=False) for i in range(100)]
        page2_threads = [_thread(f"p2-{i}", resolved=True) for i in range(7)]

        def make_response(threads, has_next, end_cursor, total):
            return {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "totalCount": total,
                            "pageInfo": {
                                "hasNextPage": has_next,
                                "endCursor": end_cursor,
                            },
                            "nodes": threads,
                        },
                    },
                },
            }

        responses = [
            make_response(page1_threads, True, "C2", 107),
            make_response(page2_threads, False, None, 107),
        ]

        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_threads._run_threads_query",
            side_effect=responses,
        ) as mock_query:
            rc = main(["--pull-request", "50"])

        assert rc == 0
        assert mock_query.call_count == 2, (
            "Pagination loop did not call the query twice; page 2 was missed"
        )
        output = _data(capsys)
        assert output["total_threads"] == 107
        assert output["unresolved_count"] == 100  # only page 1 unresolved
        assert output["resolved_count"] == 7

        ids = {t["thread_id"] for t in output["threads"]}
        assert any(i.startswith("p1-") for i in ids), "page 1 IDs missing"
        assert any(i.startswith("p2-") for i in ids), "page 2 IDs missing (cliff returned)"

    def test_pagination_cap_emits_warning_and_marks_truncated(self, capsys):
        """At-cap exit must warn the caller AND surface pagination_truncated.

        The PR #1887 retro records that a silent first:100 truncation hid 6+
        unresolved threads. A silent at-cap exit at _MAX_THREAD_PAGES would
        reproduce the same false-zero failure mode at the 5000-thread
        boundary. This test asserts: (1) the loop stops at exactly the cap;
        (2) warnings.warn fires (captured via pytest.warns); (3) the JSON
        output carries pagination_truncated=True so consumers cannot
        mistake a capped result for a complete one. The warnings.warn at
        cap is the user-visible signal; no duplicate stderr print is
        emitted (a second print would confuse JSON parsers).
        """
        cap = _mod._MAX_THREAD_PAGES

        def _page(idx: int) -> dict:
            return {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "totalCount": 999999,
                            "pageInfo": {
                                "hasNextPage": True,
                                "endCursor": f"C{idx + 1}",
                            },
                            "nodes": [_thread(f"t{idx}", resolved=False)],
                        }
                    }
                }
            }

        # Supply cap+5 page responses; loop must stop at cap.
        responses = [_page(i) for i in range(cap + 5)]

        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_threads._run_threads_query",
            side_effect=responses,
        ) as mock_query:
            with pytest.warns(UserWarning, match=r"Hit _MAX_THREAD_PAGES"):
                rc = main(["--pull-request", "1894"])

        assert rc == 0
        assert mock_query.call_count == cap, (
            f"Loop did not stop at cap; got {mock_query.call_count}, expected {cap}"
        )
        output = _data(capsys)
        assert output["pagination_truncated"] is True, (
            "JSON output must surface pagination_truncated=True at cap"
        )
        # Partial threads still returned, not discarded. The warnings.warn
        # at cap is captured by pytest.warns above; consumers also see
        # `pagination_truncated=True` in JSON. No second stderr print line
        # is emitted (duplicate signaling would confuse parsers).
        assert len(output["threads"]) == cap

    def test_collect_all_threads_return_contract(self, caplog):
        """Document the (None, 0, False) vs ([], 0, False) distinction.

        Return contract:
        - nodes is None -> PR not found OR reviewThreads field missing
                           (distinguished in logs by reason= field, not
                            return value).
        - nodes == []   -> PR exists with zero threads (still returns a list).
        - truncated     -> True only when cap was hit with hasNextPage=true.
        """
        import logging

        # Case 1: PR not found (no pullRequest in response). Returns None
        # AND emits a logger.warning with reason=pr_not_found so an
        # operator can distinguish from a missing reviewThreads connection.
        with caplog.at_level(logging.WARNING, logger="get_pr_review_threads"):
            with patch(
                "get_pr_review_threads._run_threads_query",
                return_value={"repository": {"pullRequest": None}},
            ):
                nodes, total, truncated = _mod._collect_all_threads("o", "r", 1, 1)
        assert nodes is None
        assert total == 0
        assert truncated is False
        assert any(
            "reason=pr_not_found" in r.message for r in caplog.records
        ), "PR-not-found path must log a distinct reason for observability"
        caplog.clear()

        # Case 1b: PR exists but reviewThreads connection is missing
        # (GraphQL schema regression or permission redaction). Same return
        # shape as Case 1 (None) but distinct log reason.
        with caplog.at_level(logging.WARNING, logger="get_pr_review_threads"):
            with patch(
                "get_pr_review_threads._run_threads_query",
                return_value={
                    "repository": {"pullRequest": {"reviewThreads": None}}
                },
            ):
                nodes, total, truncated = _mod._collect_all_threads("o", "r", 1, 1)
        assert nodes is None
        assert total == 0
        assert truncated is False
        assert any(
            "reason=field_missing" in r.message for r in caplog.records
        ), "reviewThreads-missing path must log a distinct reason"
        caplog.clear()

        # Case 2: PR exists, zero threads (single page, hasNextPage=false).
        with patch(
            "get_pr_review_threads._run_threads_query",
            return_value={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "totalCount": 0,
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [],
                        }
                    }
                }
            },
        ):
            nodes, total, truncated = _mod._collect_all_threads("o", "r", 1, 1)
        assert nodes == []
        assert total == 0
        assert truncated is False

        # Case 3: pageInfo missing entirely. Loop must terminate without
        # crashing. The defensive `or {}` guard means hasNextPage defaults
        # to falsy and the loop breaks normally.
        with patch(
            "get_pr_review_threads._run_threads_query",
            return_value={
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "totalCount": 1,
                            # pageInfo intentionally absent
                            "nodes": [_thread("t1", resolved=False)],
                        }
                    }
                }
            },
        ):
            nodes, total, truncated = _mod._collect_all_threads("o", "r", 1, 1)
        assert nodes is not None
        assert len(nodes) == 1
        assert truncated is False

    def test_pagination_propagates_cursor(self):
        """Cursor from page 1 must be passed as $cursor to page 2's query."""
        page1 = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "totalCount": 2,
                        "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR_X"},
                        "nodes": [_thread("t1", resolved=False)],
                    },
                },
            },
        }
        page2 = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "totalCount": 2,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [_thread("t2", resolved=False)],
                    },
                },
            },
        }

        with patch(
            "get_pr_review_threads.assert_gh_authenticated",
        ), patch(
            "get_pr_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_threads._run_threads_query",
            side_effect=[page1, page2],
        ) as mock_query:
            main(["--pull-request", "50"])

        # On the second call, the cursor kwarg must be CURSOR_X.
        call_two_kwargs = mock_query.call_args_list[1]
        assert "CURSOR_X" in str(call_two_kwargs), (
            "endCursor from page 1 was not propagated to page 2 query"
        )


# ---------------------------------------------------------------------------
# Tests: _transform_thread
# ---------------------------------------------------------------------------

_transform_thread = _mod._transform_thread


class TestTransformThread:
    def test_thread_with_no_comments(self):
        thread = {
            "id": "PRRT_1",
            "isResolved": False,
            "isOutdated": False,
            "path": "file.py",
            "line": 5,
            "startLine": None,
            "diffSide": "RIGHT",
            "comments": {"totalCount": 0, "nodes": []},
        }
        result = _transform_thread(thread, include_comments=False)
        assert result["first_comment_id"] is None
        assert result["first_comment_author"] is None
        assert result["first_comment_body"] is None
        assert result["comments"] is None

    def test_thread_with_missing_author(self):
        thread = _thread()
        thread["comments"]["nodes"][0]["author"] = None
        result = _transform_thread(thread, include_comments=False)
        assert result["first_comment_author"] is None

    def test_include_comments_with_missing_author(self):
        thread = _thread()
        thread["comments"]["nodes"][0]["author"] = None
        result = _transform_thread(thread, include_comments=True)
        assert result["comments"][0]["author"] is None

    def test_thread_with_multiple_comments(self):
        thread = _thread()
        thread["comments"]["nodes"].append({
            "id": "C2",
            "databaseId": 200,
            "body": "reply",
            "author": {"login": "bob"},
            "createdAt": "2025-01-02T00:00:00Z",
            "updatedAt": "2025-01-02T00:00:00Z",
        })
        thread["comments"]["totalCount"] = 2
        result = _transform_thread(thread, include_comments=True)
        assert len(result["comments"]) == 2
        assert result["comments"][1]["author"] == "bob"
