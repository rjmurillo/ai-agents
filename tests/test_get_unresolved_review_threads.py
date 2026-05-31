"""Tests for get_unresolved_review_threads.py skill script.

The script emits a JSON object with ``unresolved_count`` and
``fetched_pages_complete``. Pagination is handled in the script (not by
the api.py helper) so the explicit completeness flag can drive the
/pr-review completion gate's pass_when expression.

Per issue #2012, each entry in ``threads`` is normalized through
``github_core.api.transform_review_thread`` into the canonical flat shape
(``thread_id``, ``is_resolved``, ``path``, ``first_comment_*``, ``comments``)
so it matches get_pr_review_threads.py and no consumer crashes on a shape
mismatch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

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


_mod = _import_script("get_unresolved_review_threads")
main = _mod.main
build_parser = _mod.build_parser


def _page(
    *, nodes: list[dict], has_next: bool, end_cursor: str | None = None,
) -> dict:
    """Build a synthetic GraphQL response page for the reviewThreads query."""
    return {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {
                        "hasNextPage": has_next,
                        "endCursor": end_cursor,
                    },
                    "nodes": nodes,
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42

    def test_owner_repo_optional(self):
        args = build_parser().parse_args([
            "--owner", "myorg", "--repo", "myrepo", "--pull-request", "1",
        ])
        assert args.owner == "myorg"
        assert args.repo == "myrepo"

    def test_include_comments_defaults_false(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.include_comments is False

    def test_include_comments_flag(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--include-comments"],
        )
        assert args.include_comments is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_negative_pr_exits_2(self):
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "-1"])
            assert exc.value.code == 2

    def test_single_page_complete(self, capsys):
        nodes = [{"id": "t1", "isResolved": False}]
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_unresolved_review_threads.gh_graphql",
            return_value=_page(nodes=nodes, has_next=False),
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["unresolved_count"] == 1
        assert output["fetched_pages_complete"] is True
        # #2012: thread is the canonical flat shape, so the id key is
        # ``thread_id`` (snake_case), not the raw GraphQL ``id``.
        assert output["threads"][0]["thread_id"] == "t1"

    def test_zero_threads_complete(self, capsys):
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_unresolved_review_threads.gh_graphql",
            return_value=_page(nodes=[], has_next=False),
        ):
            rc = main(["--pull-request", "1"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["unresolved_count"] == 0
        assert output["fetched_pages_complete"] is True
        assert output["threads"] == []

    def test_multipage_aggregates_only_unresolved(self, capsys):
        page1 = _page(
            nodes=[
                {"id": "t1", "isResolved": True},
                {"id": "t2", "isResolved": False},
            ],
            has_next=True,
            end_cursor="cur-a",
        )
        page2 = _page(
            nodes=[
                {"id": "t3", "isResolved": False},
                {"id": "t4", "isResolved": True},
            ],
            has_next=False,
        )
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_unresolved_review_threads.gh_graphql",
            side_effect=[page1, page2],
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["unresolved_count"] == 2
        assert {t["thread_id"] for t in output["threads"]} == {"t2", "t3"}
        assert output["fetched_pages_complete"] is True

    def test_graphql_error_marks_incomplete(self, capsys):
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_unresolved_review_threads.gh_graphql",
            side_effect=RuntimeError("transport failed"),
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        # On API failure we still exit 0 and let the gate's
        # fetched_pages_complete flag drive the pass/fail decision.
        assert output["fetched_pages_complete"] is False
        assert output["unresolved_count"] == 0
        # Per Copilot review: success must mirror fetched_pages_complete
        # so other consumers do not treat an incomplete snapshot as a
        # success-shaped reply.
        assert output["success"] is False

    def test_missing_cursor_marks_incomplete(self, capsys):
        # hasNextPage true but endCursor absent: cannot continue, must
        # report incomplete rather than silently truncate.
        page1 = _page(
            nodes=[{"id": "t1", "isResolved": False}],
            has_next=True,
            end_cursor=None,
        )
        with patch(
            "get_unresolved_review_threads.assert_gh_authenticated",
        ), patch(
            "get_unresolved_review_threads.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_unresolved_review_threads.gh_graphql",
            return_value=page1,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["fetched_pages_complete"] is False
        assert output["success"] is False


# ---------------------------------------------------------------------------
# Tests: canonical flat thread shape (#2012)
# ---------------------------------------------------------------------------

# A realistic unresolved node as returned by the enriched GraphQL query.
_RICH_NODE = {
    "id": "PRRT_kwDO_x",
    "isResolved": False,
    "isOutdated": False,
    "path": ".githooks/pre-push",
    "line": 1068,
    "startLine": None,
    "diffSide": "RIGHT",
    "comments": {
        "totalCount": 2,
        "nodes": [
            {
                "databaseId": 3216327001,
                "body": "first note",
                "author": {"login": "alice"},
                "createdAt": "2026-05-01T00:00:00Z",
            },
            {
                "databaseId": 3216327045,
                "body": "last note",
                "author": {"login": "bob"},
                "createdAt": "2026-05-02T00:00:00Z",
            },
        ],
    },
}


def _run_with_node(node: dict, argv: list[str], capsys) -> dict:
    """Run main() with a single-page response containing ``node``."""
    with patch(
        "get_unresolved_review_threads.assert_gh_authenticated",
    ), patch(
        "get_unresolved_review_threads.resolve_repo_params",
        return_value=RepoInfo(owner="o", repo="r"),
    ), patch(
        "get_unresolved_review_threads.gh_graphql",
        return_value=_page(nodes=[node], has_next=False),
    ):
        rc = main(argv)
    assert rc == 0
    return json.loads(capsys.readouterr().out)


class TestThreadShape:
    """The unresolved script must emit the same flat shape as the rich one."""

    _CANONICAL_KEYS = {
        "thread_id",
        "is_resolved",
        "is_outdated",
        "path",
        "line",
        "start_line",
        "diff_side",
        "comment_count",
        "first_comment_id",
        "first_comment_author",
        "first_comment_body",
        "first_comment_created_at",
        "comments",
    }

    def test_default_shape_has_canonical_keys(self, capsys):
        output = _run_with_node(_RICH_NODE, ["--pull-request", "42"], capsys)
        thread = output["threads"][0]
        assert set(thread.keys()) == self._CANONICAL_KEYS
        assert thread["thread_id"] == "PRRT_kwDO_x"
        assert thread["is_resolved"] is False
        assert thread["path"] == ".githooks/pre-push"
        assert thread["line"] == 1068
        assert thread["comment_count"] == 2
        # Without --include-comments the list is not materialized.
        assert thread["comments"] is None
        # ... but the first comment metadata is always present.
        assert thread["first_comment_author"] == "alice"
        assert thread["first_comment_body"] == "first note"

    def test_include_comments_materializes_flat_list(self, capsys):
        output = _run_with_node(
            _RICH_NODE, ["--pull-request", "42", "--include-comments"], capsys,
        )
        thread = output["threads"][0]
        assert isinstance(thread["comments"], list)
        assert len(thread["comments"]) == 2
        # This is the exact idiom that crashed in issue #2012: asking the
        # unresolved script for the last comment's author. It now works.
        assert thread["comments"][-1]["author"] == "bob"
        assert thread["comments"][-1]["body"] == "last note"
        assert thread["comments"][0]["id"] == 3216327001

    def test_matches_rich_script_transform(self, capsys):
        """The unresolved output is identical to transform_review_thread."""
        from scripts.github_core.api import transform_review_thread

        output = _run_with_node(
            _RICH_NODE, ["--pull-request", "42", "--include-comments"], capsys,
        )
        expected = transform_review_thread(_RICH_NODE, include_comments=True)
        assert output["threads"][0] == expected
