"""Tests for set_issue_relationship.py."""

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


def _node(number, repo="o/r"):
    return {
        "number": number,
        "title": "T",
        "state": "OPEN",
        "url": f"https://github.com/{repo}/issues/{number}",
        "repository": {"nameWithOwner": repo},
    }


def _conn(nodes):
    return {"totalCount": len(nodes), "nodes": list(nodes)}


def _source_data(
    number=5,
    issue_id="SRC1",
    parent=None,
    sub_issues=(),
    blocked_by=(),
    blocking=(),
    relates_to=(),
):
    return {
        "repository": {
            "issue": {
                "id": issue_id,
                "number": number,
                "title": "Source",
                "state": "OPEN",
                "parent": parent,
                "subIssues": _conn(sub_issues),
                "blockedBy": _conn(blocked_by),
                "blocking": _conn(blocking),
                "relatesTo": _conn(relates_to),
            }
        }
    }


def _target_payload(node_id="TGT1", number=100, parent=None, typename="Issue"):
    if typename != "Issue":
        return {"repository": {"issueOrPullRequest": {"__typename": typename}}}
    return {
        "repository": {
            "issueOrPullRequest": {
                "__typename": "Issue",
                "id": node_id,
                "number": number,
                "parent": parent,
            }
        }
    }


def _target_key(number, owner="o", repo="r"):
    return (owner.lower(), repo.lower(), number)


class GraphQLStub:
    """Dispatches gh_graphql calls by query shape.

    ``source`` answers the RELATIONSHIPS_QUERY (the --issue side); ``targets``
    is a ``{(owner_lower, repo_lower, number): payload}`` map answering the
    TARGET_QUERY; any other call is a mutation, routed through
    ``mutation_side_effect``. A value that is a BaseException is raised
    instead of returned.
    """

    def __init__(self, source, targets=None, mutation_side_effect=None):
        self.source = source
        self.targets = targets or {}
        self.mutation_calls: list[tuple[str, dict]] = []
        self._mutation_side_effect = mutation_side_effect or (lambda query, variables: {})

    def __call__(self, query, variables=None):
        variables = dict(variables or {})
        if "issueOrPullRequest" in query:
            key = (variables["owner"].lower(), variables["repo"].lower(), variables["number"])
            resp = self.targets.get(key)
            if resp is None:
                return {"repository": {"issueOrPullRequest": None}}
            if isinstance(resp, BaseException):
                raise resp
            return resp
        if "subIssues(first" in query:
            if isinstance(self.source, BaseException):
                raise self.source
            return self.source
        self.mutation_calls.append((query, variables))
        return self._mutation_side_effect(query, variables)


@pytest.fixture
def _import_module():
    import importlib

    mod_name = "set_issue_relationship"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def _run(mod, argv, stub):
    with (
        patch("set_issue_relationship.assert_gh_authenticated"),
        patch("set_issue_relationship.resolve_repo_params", return_value=_mock_repo()),
        patch("get_issue_relationships.gh_graphql", side_effect=stub),
        patch("set_issue_relationship.gh_graphql", side_effect=stub),
    ):
        return mod.main(argv)


def _out(capsys):
    return json.loads(capsys.readouterr().out)


class TestSetIssueRelationshipAdd:
    """Adding each of the five relation kinds, correct mutation and id order."""

    def test_add_parent_target_id_first(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            ["--issue", "5", "--relation", "parent", "--target", "100", "--output-format", "json"],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "linked"
        assert len(stub.mutation_calls) == 1
        query, variables = stub.mutation_calls[0]
        assert "addSubIssue" in query
        assert variables == {"a": "TGT1", "b": "SRC1"}

    def test_add_sub_issue_source_id_first(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "addSubIssue" in query
        assert variables == {"a": "SRC1", "b": "TGT1"}

    def test_add_blocked_by_source_id_first(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "blocked-by",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "addBlockedBy" in query
        assert variables == {"a": "SRC1", "b": "TGT1"}

    def test_add_blocking_target_id_first(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "blocking",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "addBlockedBy" in query
        assert variables == {"a": "TGT1", "b": "SRC1"}

    def test_add_relates_to_source_id_first(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "addRelatesTo" in query
        assert variables == {"a": "SRC1", "b": "TGT1"}


class TestSetIssueRelationshipRemove:
    """Removing each of the five relation kinds."""

    def test_remove_parent(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(parent=_node(100)),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "parent",
                "--target",
                "100",
                "--remove",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "unlinked"
        query, variables = stub.mutation_calls[0]
        assert "removeSubIssue" in query
        assert variables == {"a": "TGT1", "b": "SRC1"}

    def test_remove_sub_issue(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(sub_issues=[_node(100)]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "100",
                "--remove",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "removeSubIssue" in query
        assert variables == {"a": "SRC1", "b": "TGT1"}

    def test_remove_blocked_by(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(blocked_by=[_node(100)]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "blocked-by",
                "--target",
                "100",
                "--remove",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "removeBlockedBy" in query
        assert variables == {"a": "SRC1", "b": "TGT1"}

    def test_remove_blocking(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(blocking=[_node(100)]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "blocking",
                "--target",
                "100",
                "--remove",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "removeBlockedBy" in query
        assert variables == {"a": "TGT1", "b": "SRC1"}

    def test_remove_relates_to(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[_node(100)]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--remove",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        query, variables = stub.mutation_calls[0]
        assert "removeRelatesTo" in query
        assert variables == {"a": "SRC1", "b": "TGT1"}


class TestSetIssueRelationshipNoOpsAndDryRun:
    def test_already_linked_no_mutation(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(sub_issues=[_node(100)]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "already_linked"
        assert stub.mutation_calls == []

    def test_not_linked_remove_no_mutation(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(blocked_by=[]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "blocked-by",
                "--target",
                "100",
                "--remove",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "not_linked"
        assert stub.mutation_calls == []

    def test_dry_run_would_link(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--dry-run",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "would_link"
        assert result["Data"]["dry_run"] is True
        assert stub.mutation_calls == []

    def test_dry_run_would_unlink(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[_node(100)]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--dry-run",
                "--remove",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "would_unlink"
        assert stub.mutation_calls == []


class TestSetIssueRelationshipTargets:
    def test_multiple_targets(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[]),
            targets={
                _target_key(101): _target_payload("TGT101", 101),
                _target_key(102): _target_payload("TGT102", 102),
            },
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "101",
                "102",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        actions = {r["target"]: r["action"] for r in result["Data"]["results"]}
        assert actions == {"o/r#101": "linked", "o/r#102": "linked"}
        assert result["Data"]["failed"] == []
        assert len(stub.mutation_calls) == 2

    def test_target_format_bare_number(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["target"] == "o/r#100"

    def test_target_format_hash_number(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "#100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["target"] == "o/r#100"

    def test_target_format_cross_repo(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[]),
            targets={_target_key(100, owner="other", repo="repo2"): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "other/repo2#100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["target"] == "other/repo2#100"

    def test_target_format_invalid_exits_1(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=AssertionError("gh_graphql should not be called"))
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "abc",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert result["Error"]["Type"] == "InvalidParams"
        assert "Invalid target" in result["Error"]["Message"]
        assert stub.mutation_calls == []

    def test_target_zero_exits_1(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=AssertionError("gh_graphql should not be called"))
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "0",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert result["Error"]["Type"] == "InvalidParams"

    def test_self_link_rejected(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=AssertionError("gh_graphql should not be called"))
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "5",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert result["Error"]["Type"] == "InvalidParams"
        assert "itself" in result["Error"]["Message"]

    def test_pr_target_rejected(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(relates_to=[]),
            targets={_target_key(100): _target_payload(typename="PullRequest")},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert result["Error"]["Type"] == "InvalidParams"
        assert "pull request" in result["Error"]["Message"]

    def test_missing_target_not_found(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=_source_data(relates_to=[]), targets={})
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "999",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 2
        result = _out(capsys)
        assert result["Error"]["Type"] == "NotFound"


class TestSetIssueRelationshipValidation:
    def test_issue_zero_exits_1(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=AssertionError("gh_graphql should not be called"))
        rc = _run(
            mod,
            [
                "--issue",
                "0",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert result["Error"]["Type"] == "InvalidParams"
        assert stub.mutation_calls == []

    def test_parent_with_two_targets_rejected(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=AssertionError("gh_graphql should not be called"))
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "parent",
                "--target",
                "101",
                "102",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert "exactly one --target" in result["Error"]["Message"]

    def test_replace_parent_with_remove_rejected(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=AssertionError("gh_graphql should not be called"))
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "parent",
                "--target",
                "100",
                "--remove",
                "--replace-parent",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert "--replace-parent applies only" in result["Error"]["Message"]

    def test_replace_parent_with_non_parent_relation_rejected(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=AssertionError("gh_graphql should not be called"))
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "blocked-by",
                "--target",
                "100",
                "--replace-parent",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert "--replace-parent applies only" in result["Error"]["Message"]


class TestSetIssueRelationshipParentConflict:
    def test_parent_conflict_without_replace_parent(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(parent=_node(999)),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            ["--issue", "5", "--relation", "parent", "--target", "100", "--output-format", "json"],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert result["Error"]["Type"] == "InvalidParams"
        assert "o/r#999" in result["Error"]["Message"]
        assert "already the parent" in result["Error"]["Message"]
        assert stub.mutation_calls == []

    def test_parent_conflict_with_replace_parent_moves(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(parent=_node(999)),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "parent",
                "--target",
                "100",
                "--replace-parent",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "linked"
        query, variables = stub.mutation_calls[0]
        assert "replaceParent: true" in query
        assert "addSubIssue" in query
        assert variables == {"a": "TGT1", "b": "SRC1"}

    def test_sub_issue_target_has_other_parent_conflict(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(sub_issues=[]),
            targets={
                _target_key(100): _target_payload(
                    "TGT1", 100, parent={"number": 50, "repository": {"nameWithOwner": "o/r"}}
                )
            },
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 1
        result = _out(capsys)
        assert "o/r#50" in result["Error"]["Message"]
        assert "already the parent" in result["Error"]["Message"]
        assert stub.mutation_calls == []

    def test_sub_issue_conflict_with_replace_parent_moves(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(sub_issues=[]),
            targets={
                _target_key(100): _target_payload(
                    "TGT1", 100, parent={"number": 50, "repository": {"nameWithOwner": "o/r"}}
                )
            },
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "100",
                "--replace-parent",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "linked"
        query, variables = stub.mutation_calls[0]
        assert "replaceParent: true" in query
        assert "addSubIssue" in query
        assert variables == {"a": "SRC1", "b": "TGT1"}

    def test_sub_issue_target_parent_is_source_already_linked(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(sub_issues=[_node(100)]),
            targets={
                _target_key(100): _target_payload(
                    "TGT1", 100, parent={"number": 5, "repository": {"nameWithOwner": "o/r"}}
                )
            },
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "already_linked"
        assert stub.mutation_calls == []

    def test_sub_issue_target_parent_equals_source_but_not_listed_no_conflict(
        self, _import_module, capsys
    ):
        """Desync case: target's parent already names source, but source's own
        sub_issues list does not (yet) list it. No conflict should be raised;
        the add proceeds (and is effectively idempotent on GitHub's side).
        """
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(sub_issues=[]),
            targets={
                _target_key(100): _target_payload(
                    "TGT1", 100, parent={"number": 5, "repository": {"nameWithOwner": "o/r"}}
                )
            },
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "linked"
        query, variables = stub.mutation_calls[0]
        assert "replaceParent: true" not in query
        assert variables == {"a": "SRC1", "b": "TGT1"}


class TestSetIssueRelationshipCaseInsensitivity:
    def test_case_insensitive_owner_repo_matching(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(
            source=_source_data(sub_issues=[_node(100, repo="o/r")]),
            targets={_target_key(100): _target_payload("TGT1", 100)},
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "sub-issue",
                "--target",
                "O/R#100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 0
        result = _out(capsys)
        assert result["Data"]["results"][0]["action"] == "already_linked"
        assert stub.mutation_calls == []


class TestSetIssueRelationshipFailures:
    def test_failing_mutation_exits_3_others_processed(self, _import_module, capsys):
        mod = _import_module

        def mutation_side_effect(query, variables):
            if variables.get("b") == "TGT201":
                raise RuntimeError("mutation failed")
            return {}

        stub = GraphQLStub(
            source=_source_data(relates_to=[]),
            targets={
                _target_key(201): _target_payload("TGT201", 201),
                _target_key(202): _target_payload("TGT202", 202),
            },
            mutation_side_effect=mutation_side_effect,
        )
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "201",
                "202",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 3
        result = _out(capsys)
        assert result["Error"]["Type"] == "ApiError"
        data = result["Data"]
        assert data["failed"] == ["o/r#201"]
        by_target = {r["target"]: r for r in data["results"]}
        assert by_target["o/r#201"]["action"] == "failed"
        assert "mutation failed" in by_target["o/r#201"]["error"]
        assert by_target["o/r#202"]["action"] == "linked"
        assert len(stub.mutation_calls) == 2

    def test_fetch_relationships_runtime_error_exits_3(self, _import_module, capsys):
        mod = _import_module
        stub = GraphQLStub(source=RuntimeError("upstream down"), targets={})
        rc = _run(
            mod,
            [
                "--issue",
                "5",
                "--relation",
                "relates-to",
                "--target",
                "100",
                "--output-format",
                "json",
            ],
            stub,
        )
        assert rc == 3
        result = _out(capsys)
        assert result["Error"]["Type"] == "ApiError"
        assert result["Error"]["Message"] == "upstream down"
