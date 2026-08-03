"""Tests for get_pr_reviews.py skill script (issue #4378)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)

_MODULE = "get_pr_reviews"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script(_MODULE)
main = _mod.main
build_parser = _mod.build_parser


def _api_review(
    login: str = "alice",
    state: str = "APPROVED",
    body: str = "ship it",
    review_id: int = 1,
    author_id: int | None = None,
):
    return {
        "id": review_id,
        "node_id": f"PRR_node{review_id}",
        "user": {"login": login, "id": author_id},
        "state": state,
        "body": body,
        "submitted_at": "2026-08-01T00:00:00Z",
        "html_url": f"https://github.com/o/r/pull/1#pullrequestreview-{review_id}",
        "commit_id": "deadbeef",
    }


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _run(reviews, argv):
    with patch(f"{_MODULE}.assert_gh_authenticated"), patch(
        f"{_MODULE}.resolve_repo_params",
        return_value=RepoInfo(owner="o", repo="r"),
    ), patch(
        f"{_MODULE}.gh_api_paginated",
        return_value=reviews,
    ):
        return main(argv)


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_state_defaults_to_empty(self):
        args = build_parser().parse_args(["--pull-request", "7"])
        assert args.state == ""


class TestMain:
    def test_returns_verdict_state_and_body(self, capsys):
        rc = _run(
            [_api_review(state="CHANGES_REQUESTED", body="needs work")],
            ["--pull-request", "1", "--output-format", "json"],
        )
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 1
        review = data["reviews"][0]
        assert review["state"] == "CHANGES_REQUESTED"
        assert review["body"] == "needs work"
        assert review["id"] == 1
        assert review["nodeId"] == "PRR_node1"
        assert review["submittedAt"] == "2026-08-01T00:00:00Z"
        assert review["commitId"] == "deadbeef"

    def test_state_filter_keeps_only_matching(self, capsys):
        rc = _run(
            [
                _api_review(state="APPROVED", review_id=1),
                _api_review(state="COMMENTED", review_id=2),
            ],
            ["--pull-request", "1", "--state", "approved", "--output-format", "json"],
        )
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 1
        assert data["reviews"][0]["state"] == "APPROVED"

    def test_invalid_state_exits_1(self, capsys):
        rc = _run(
            [_api_review()],
            ["--pull-request", "1", "--state", "NOPE", "--output-format", "json"],
        )
        assert rc == 1
        assert _envelope(capsys)["Success"] is False

    def test_not_authenticated_exits_4(self):
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_no_reviews_is_success_with_zero_count(self, capsys):
        rc = _run([], ["--pull-request", "1", "--output-format", "json"])
        assert rc == 0
        assert _envelope(capsys)["Data"]["count"] == 0

    def test_all_pages_are_returned(self, capsys):
        many = [_api_review(review_id=i) for i in range(150)]
        rc = _run(many, ["--pull-request", "1", "--output-format", "json"])
        assert rc == 0
        assert _envelope(capsys)["Data"]["count"] == 150

    def test_copilot_alias_author_is_canonicalized(self, capsys):
        rc = _run(
            [_api_review(login="Copilot", author_id=175728472)],
            ["--pull-request", "1", "--output-format", "json"],
        )
        assert rc == 0
        review = _envelope(capsys)["Data"]["reviews"][0]
        assert review["author"] == "github-copilot[bot]"
        assert review["authorId"] == 175728472
        assert review["authorObserved"] == "Copilot"

    def test_account_id_separates_two_authors_reported_as_copilot(self, capsys):
        rc = _run(
            [
                _api_review(login="Copilot", author_id=175728472, review_id=1),
                _api_review(login="Copilot", author_id=198982749, review_id=2),
            ],
            ["--pull-request", "1", "--output-format", "json"],
        )
        assert rc == 0
        reviews = _envelope(capsys)["Data"]["reviews"]
        assert [review["author"] for review in reviews] == [
            "github-copilot[bot]",
            "copilot-swe-agent[bot]",
        ]

    def test_missing_user_and_null_body_do_not_raise(self, capsys):
        rc = _run(
            [{"id": 9, "node_id": "n", "user": None, "state": "DISMISSED", "body": None}],
            ["--pull-request", "1", "--output-format", "json"],
        )
        assert rc == 0
        review = _envelope(capsys)["Data"]["reviews"][0]
        assert review["author"] is None
        assert review["authorId"] is None
        assert review["body"] == ""
