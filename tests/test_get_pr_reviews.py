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


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_pr_reviews")
main = _mod.main
build_parser = _mod.build_parser
_normalize = _mod._normalize
_canonicalize_login = _mod._canonicalize_login


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _api_review(login: str, state: str, body: str, rid: int = 1, node: str = "RN_1"):
    return {
        "id": rid,
        "node_id": node,
        "user": {"login": login},
        "state": state,
        "body": body,
        "submitted_at": "2026-06-01T00:00:00Z",
        "html_url": f"https://github.com/o/r/pull/10#pullrequestreview-{rid}",
    }


def _slurped(*pages: list):
    return _completed(stdout=json.dumps(list(pages)), rc=0)


def _fake_repo():
    return type("R", (), {"owner": "o", "repo": "r"})()


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_defaults(self):
        args = build_parser().parse_args(["--pull-request", "99"])
        assert args.pull_request == 99
        assert args.owner == ""
        assert args.repo == ""


class TestNormalize:
    def test_fields_present(self):
        item = _api_review("alice", "APPROVED", "LGTM", rid=42, node="RN_42")
        out = _normalize(item)
        assert out["id"] == 42
        assert out["node_id"] == "RN_42"
        assert out["author"] == "alice"
        assert out["state"] == "APPROVED"
        assert out["body"] == "LGTM"
        assert out["submittedAt"] == "2026-06-01T00:00:00Z"
        assert "pull/10#" in out["url"]

    def test_empty_body_normalized(self):
        item = _api_review("alice", "COMMENTED", None)
        item["body"] = None
        out = _normalize(item)
        assert out["body"] == ""

    def test_missing_user_yields_empty_author(self):
        item = _api_review("alice", "APPROVED", "")
        del item["user"]
        out = _normalize(item)
        assert out["author"] == ""

    def test_no_aliases_for_regular_user(self):
        item = _api_review("rjmurillo", "APPROVED", "")
        out = _normalize(item)
        assert out["aliases"] == []


class TestBotAliasCanonicalisation:
    def test_copilot_alias_canonicalised(self):
        canonical, aliases = _canonicalize_login("copilot-pull-request-reviewer")
        assert canonical == "Copilot"
        assert "copilot-pull-request-reviewer" in aliases

    def test_known_alias_in_normalize(self):
        item = _api_review("copilot-pull-request-reviewer", "APPROVED", "")
        out = _normalize(item)
        assert out["author"] == "Copilot"
        assert out["aliases"] == ["copilot-pull-request-reviewer"]

    def test_unknown_login_passes_through(self):
        canonical, aliases = _canonicalize_login("some-human")
        assert canonical == "some-human"
        assert aliases == []


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch("get_pr_reviews.assert_gh_authenticated", side_effect=SystemExit(4)):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_returns_reviews_envelope(self, capsys):
        page = [
            _api_review("alice", "APPROVED", "LGTM", rid=1, node="RN_1"),
            _api_review("bob", "REQUEST_CHANGES", "Fix this", rid=2, node="RN_2"),
        ]
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run", return_value=_slurped(page)):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        out = _envelope(capsys)
        data = out["Data"]
        assert data["count"] == 2
        assert data["pull_request"] == 10
        reviews = data["reviews"]
        assert reviews[0]["author"] == "alice"
        assert reviews[0]["state"] == "APPROVED"
        assert reviews[1]["state"] == "REQUEST_CHANGES"

    def test_empty_reviews(self, capsys):
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run", return_value=_slurped([])):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        out = _envelope(capsys)
        assert out["Data"]["count"] == 0
        assert out["Data"]["reviews"] == []

    def test_api_failure_exits_3(self):
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run", return_value=_completed(rc=1, stderr="server error")):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
            assert exc.value.code == 3

    def test_not_found_exits_2(self):
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run",
                   return_value=_completed(rc=1, stderr="Could not resolve not found")):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
            assert exc.value.code == 2

    def test_auth_error_exits_4(self):
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run",
                   return_value=_completed(rc=1, stderr="not logged in")):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
            assert exc.value.code == 4

    def test_invalid_json_exits_3(self):
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run",
                   return_value=_completed(rc=0, stdout="not-json")):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "10"])
            assert exc.value.code == 3


class TestPagination:
    def test_multiple_pages_flattened(self, capsys):
        page1 = [_api_review("alice", "APPROVED", "", rid=1)]
        page2 = [_api_review("bob", "REQUEST_CHANGES", "", rid=2)]
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run", return_value=_slurped(page1, page2)):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        out = _envelope(capsys)
        assert out["Data"]["count"] == 2

    def test_single_page_not_wrapped(self, capsys):
        """When gh api --slurp returns a single-element list, still flatten correctly."""
        page = [_api_review("carol", "COMMENTED", "see inline", rid=3)]
        with patch("get_pr_reviews.assert_gh_authenticated"), \
             patch("get_pr_reviews.resolve_repo_params", return_value=_fake_repo()), \
             patch("subprocess.run", return_value=_completed(stdout=json.dumps([page]))):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        out = _envelope(capsys)
        assert out["Data"]["count"] == 1
        assert out["Data"]["reviews"][0]["author"] == "carol"
