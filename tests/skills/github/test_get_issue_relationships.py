"""Tests for get_issue_relationships.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure importability
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (str(_lib_dir), str(_scripts_dir / "issue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


def _node(number, repo="o/r", title="T", state="OPEN"):
    return {
        "number": number,
        "title": title,
        "state": state,
        "url": f"https://github.com/{repo}/issues/{number}",
        "repository": {"nameWithOwner": repo},
    }


def _conn(nodes):
    return {"totalCount": len(nodes), "nodes": list(nodes)}


def _issue_data(
    number=5,
    title="Source",
    state="OPEN",
    parent=None,
    sub_issues=(),
    blocked_by=(),
    blocking=(),
    relates_to=(),
    issue_id="ID1",
):
    return {
        "repository": {
            "issue": {
                "id": issue_id,
                "number": number,
                "title": title,
                "state": state,
                "parent": parent,
                "subIssues": _conn(sub_issues),
                "blockedBy": _conn(blocked_by),
                "blocking": _conn(blocking),
                "relatesTo": _conn(relates_to),
            }
        }
    }


@pytest.fixture
def _import_module():
    import importlib

    mod_name = "get_issue_relationships"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestGetIssueRelationships:
    """Tests for get_issue_relationships.main."""

    def test_success_full_envelope(self, _import_module, capsys):
        mod = _import_module
        data = _issue_data(
            parent=_node(1),
            sub_issues=[_node(2), _node(3)],
            blocked_by=[_node(4)],
            blocking=[_node(6)],
            relates_to=[_node(7), _node(8), _node(9)],
        )
        with (
            patch("get_issue_relationships.assert_gh_authenticated"),
            patch("get_issue_relationships.resolve_repo_params", return_value=_mock_repo()),
            patch("get_issue_relationships.gh_graphql", return_value=data),
        ):
            rc = mod.main(["--issue", "5", "--output-format", "json"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is True
        d = result["Data"]
        assert "id" not in d
        assert d["number"] == 5
        assert d["parent"]["number"] == 1
        assert d["parent"]["repository"] == "o/r"
        assert [n["number"] for n in d["sub_issues"]] == [2, 3]
        assert d["sub_issues_total"] == 2
        assert [n["number"] for n in d["blocked_by"]] == [4]
        assert d["blocked_by_total"] == 1
        assert [n["number"] for n in d["blocking"]] == [6]
        assert d["blocking_total"] == 1
        assert [n["number"] for n in d["relates_to"]] == [7, 8, 9]
        assert d["relates_to_total"] == 3

    def test_parent_none(self, _import_module, capsys):
        mod = _import_module
        data = _issue_data(parent=None)
        with (
            patch("get_issue_relationships.assert_gh_authenticated"),
            patch("get_issue_relationships.resolve_repo_params", return_value=_mock_repo()),
            patch("get_issue_relationships.gh_graphql", return_value=data),
        ):
            rc = mod.main(["--issue", "5", "--output-format", "json"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["parent"] is None

    def test_issue_null_exits_2_not_found(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("get_issue_relationships.assert_gh_authenticated"),
            patch("get_issue_relationships.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "get_issue_relationships.gh_graphql",
                return_value={"repository": {"issue": None}},
            ),
        ):
            rc = mod.main(["--issue", "5", "--output-format", "json"])
        assert rc == 2
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is False
        assert result["Error"]["Code"] == 2
        assert result["Error"]["Type"] == "NotFound"

    def test_could_not_resolve_exits_2_not_found(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("get_issue_relationships.assert_gh_authenticated"),
            patch("get_issue_relationships.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "get_issue_relationships.gh_graphql",
                side_effect=RuntimeError("Could not resolve to an Issue"),
            ),
        ):
            rc = mod.main(["--issue", "5", "--output-format", "json"])
        assert rc == 2
        result = json.loads(capsys.readouterr().out)
        assert result["Error"]["Type"] == "NotFound"

    def test_other_runtime_error_exits_3_api_error(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("get_issue_relationships.assert_gh_authenticated"),
            patch("get_issue_relationships.resolve_repo_params", return_value=_mock_repo()),
            patch("get_issue_relationships.gh_graphql", side_effect=RuntimeError("boom")),
        ):
            rc = mod.main(["--issue", "5", "--output-format", "json"])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Error"]["Type"] == "ApiError"
        assert result["Error"]["Message"] == "boom"

    def test_empty_message_runtime_error_gets_fallback_message(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("get_issue_relationships.assert_gh_authenticated"),
            patch("get_issue_relationships.resolve_repo_params", return_value=_mock_repo()),
            patch("get_issue_relationships.gh_graphql", side_effect=RuntimeError("")),
        ):
            rc = mod.main(["--issue", "5", "--output-format", "json"])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Error"]["Message"] == "GraphQL request failed"

    def test_issue_zero_exits_1_invalid_params(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("get_issue_relationships.assert_gh_authenticated") as auth,
            patch("get_issue_relationships.resolve_repo_params") as resolve,
        ):
            rc = mod.main(["--issue", "0", "--output-format", "json"])
        assert rc == 1
        result = json.loads(capsys.readouterr().out)
        assert result["Error"]["Type"] == "InvalidParams"
        auth.assert_not_called()
        resolve.assert_not_called()

    def test_human_summary_text(self, _import_module, capsys):
        mod = _import_module
        data = _issue_data(
            number=5,
            parent=_node(1),
            sub_issues=[_node(2)],
            blocked_by=[_node(4)],
            blocking=[_node(6)],
            relates_to=[_node(7)],
        )
        with (
            patch("get_issue_relationships.assert_gh_authenticated"),
            patch("get_issue_relationships.resolve_repo_params", return_value=_mock_repo()),
            patch("get_issue_relationships.gh_graphql", return_value=data),
        ):
            rc = mod.main(["--issue", "5", "--output-format", "human"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Issue #5" in out
        assert "parent #1" in out
        assert "sub_issues 1" in out
        assert "blocked_by 1" in out
        assert "blocking 1" in out
        assert "relates_to 1" in out
