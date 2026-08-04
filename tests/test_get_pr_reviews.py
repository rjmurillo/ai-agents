"""Tests for get_pr_reviews.py skill script (issue #4378)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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
_normalize = _mod._normalize


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _api_review(
    login: str = "alice",
    state: str = "APPROVED",
    body: str | None = "ship it",
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


def _slurped(*pages: list[dict]):
    return _completed(stdout=json.dumps(list(pages)), rc=0)


def _fake_repo():
    return type("R", (), {"owner": "o", "repo": "r"})()


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _run(reviews, argv):
    with patch(f"{_MODULE}.assert_gh_authenticated"), patch(
        f"{_MODULE}.resolve_repo_params",
        return_value=_fake_repo(),
    ), patch(
        f"{_MODULE}.subprocess.run",
        return_value=_slurped(reviews),
    ):
        return main(argv)


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_defaults(self):
        args = build_parser().parse_args(["--pull-request", "99"])
        assert args.pull_request == 99
        assert args.owner == ""
        assert args.repo == ""
        assert args.state == ""


class TestNormalize:
    def test_fields_present(self):
        out = _normalize(_api_review(review_id=42, author_id=101))
        assert out == {
            "id": 42,
            "node_id": "PRR_node42",
            "author": "alice",
            "aliases": [],
            "author_id": 101,
            "author_observed": "alice",
            "state": "APPROVED",
            "body": "ship it",
            "submittedAt": "2026-08-01T00:00:00Z",
            "url": "https://github.com/o/r/pull/1#pullrequestreview-42",
            "commit_id": "deadbeef",
        }

    def test_empty_body_normalized(self):
        assert _normalize(_api_review(body=None))["body"] == ""

    def test_missing_user_yields_none_identity(self):
        item = _api_review()
        item["user"] = None
        out = _normalize(item)
        assert out["author"] is None
        assert out["aliases"] == []
        assert out["author_id"] is None
        assert out["author_observed"] is None

    def test_aliases_api_is_preserved_with_additive_identity_fields(self):
        out = _normalize(
            _api_review(
                login="copilot-pull-request-reviewer",
                author_id=175728472,
            )
        )
        assert out["author"] == "github-copilot[bot]"
        assert out["aliases"] == ["copilot-pull-request-reviewer"]
        assert out["author_id"] == 175728472
        assert out["author_observed"] == "copilot-pull-request-reviewer"

    def test_account_id_separates_two_authors_reported_as_copilot(self):
        reviewer = _normalize(_api_review(login="Copilot", author_id=175728472))
        coding_agent = _normalize(_api_review(login="Copilot", author_id=198982749))
        assert reviewer["author"] == "github-copilot[bot]"
        assert coding_agent["author"] == "copilot-swe-agent[bot]"
        assert reviewer["aliases"] == coding_agent["aliases"] == ["Copilot"]
        assert reviewer["author_observed"] == coding_agent["author_observed"] == "Copilot"


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(f"{_MODULE}.assert_gh_authenticated", side_effect=SystemExit(4)):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_returns_reviews_envelope(self, capsys):
        page = [
            _api_review("alice", "APPROVED", "LGTM", review_id=1),
            _api_review("bob", "CHANGES_REQUESTED", "Fix this", review_id=2),
        ]
        assert _run(page, ["--pull-request", "10"]) == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 2
        assert data["pull_request"] == 10
        assert [review["state"] for review in data["reviews"]] == [
            "APPROVED",
            "CHANGES_REQUESTED",
        ]

    def test_state_filter_keeps_only_matching(self, capsys):
        page = [
            _api_review(state="APPROVED", review_id=1),
            _api_review(state="COMMENTED", review_id=2),
        ]
        assert _run(page, ["--pull-request", "10", "--state", "approved"]) == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 1
        assert data["reviews"][0]["state"] == "APPROVED"

    def test_invalid_state_exits_1(self, capsys):
        assert _run([], ["--pull-request", "10", "--state", "NOPE"]) == 1
        assert _envelope(capsys)["Success"] is False

    def test_empty_reviews(self, capsys):
        assert _run([], ["--pull-request", "10"]) == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 0
        assert data["reviews"] == []

    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            ("server error", 3),
            ("Could not resolve not found", 2),
            ("not logged in", 4),
        ],
    )
    def test_api_failure_exit_codes(self, stderr, expected):
        with patch(f"{_MODULE}.assert_gh_authenticated"), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=_fake_repo(),
        ), patch(
            f"{_MODULE}.subprocess.run",
            return_value=_completed(rc=1, stderr=stderr),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
            assert exc.value.code == expected

    def test_invalid_json_exits_3(self):
        with patch(f"{_MODULE}.assert_gh_authenticated"), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=_fake_repo(),
        ), patch(
            f"{_MODULE}.subprocess.run",
            return_value=_completed(stdout="not-json"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
            assert exc.value.code == 3


class TestPagination:
    def test_multiple_pages_flattened(self, capsys):
        page1 = [_api_review("alice", "APPROVED", "", review_id=1)]
        page2 = [_api_review("bob", "CHANGES_REQUESTED", "", review_id=2)]
        with patch(f"{_MODULE}.assert_gh_authenticated"), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=_fake_repo(),
        ), patch(
            f"{_MODULE}.subprocess.run",
            return_value=_slurped(page1, page2),
        ):
            assert main(["--pull-request", "10"]) == 0
        assert _envelope(capsys)["Data"]["count"] == 2

    def test_single_page_not_wrapped(self, capsys):
        page = [_api_review("carol", "COMMENTED", "see inline", review_id=3)]
        with patch(f"{_MODULE}.assert_gh_authenticated"), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=_fake_repo(),
        ), patch(
            f"{_MODULE}.subprocess.run",
            return_value=_completed(stdout=json.dumps([page])),
        ):
            assert main(["--pull-request", "10"]) == 0
        reviews = _envelope(capsys)["Data"]["reviews"]
        assert len(reviews) == 1
        assert reviews[0]["author"] == "carol"
