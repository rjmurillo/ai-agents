"""Stacked PRs never reach T1 (issue #6201).

A squash merge folds a PR into its base. For a stacked PR the base is the parent
PR's branch, so the T1 route in pr-autofix would collapse the stack. The tier
classifier therefore returns STACKED in place of T1 when the base is not the
repository default branch, and keeps every other tier unchanged.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.test_test_pr_merge_ready import (
    _OPEN_PR,
    _mod,
    check_merge_readiness,
    classify_tier,
    main,
)


def _payload(
    *,
    base: object = "main",
    default: object = "main",
    merge_state: str = "CLEAN",
    default_ref: object = "unset",
) -> dict:
    """`_OPEN_PR` with the base and default branch names under test."""
    pr_data = json.loads(json.dumps(_OPEN_PR))
    node = pr_data["repository"]["pullRequest"]
    node["baseRefName"] = base
    node["mergeStateStatus"] = merge_state
    node["baseRepository"] = {
        "defaultBranchRef": {"name": default} if default_ref == "unset" else default_ref
    }
    return pr_data


def _readiness(pr_data: dict, **kwargs) -> dict:
    with patch("test_pr_merge_ready.gh_graphql", return_value=pr_data):
        return check_merge_readiness("o", "r", 42, **kwargs)


class TestStackedReplacesT1:
    def test_default_base_is_still_t1(self):
        result = _readiness(_payload())

        assert result["Tier"] == "T1"
        assert result["BaseRef"] == "main"
        assert result["DefaultBranch"] == "main"

    @pytest.mark.parametrize("merge_state", ["CLEAN", "HAS_HOOKS", "UNSTABLE"])
    def test_every_t1_state_is_stacked_when_the_base_is_a_feature_branch(self, merge_state):
        result = _readiness(_payload(base="feature/parent", merge_state=merge_state))

        assert result["Tier"] == "STACKED"
        assert result["BaseRef"] == "feature/parent"
        assert result["DefaultBranch"] == "main"

    def test_can_merge_stays_true_so_stack_members_pass_the_merge_pr_gate(self):
        result = _readiness(_payload(base="feature/parent"))

        assert result["CanMerge"] is True
        assert result["Reasons"] == []

    def test_bot_author_on_a_stacked_clean_pr_is_stacked(self):
        result = _readiness(_payload(base="feature/parent"), is_bot=True)

        assert result["Tier"] == "STACKED"

    def test_exit_code_is_zero_for_a_mergeable_stacked_pr(self, capsys):
        with (
            patch("test_pr_merge_ready.assert_gh_authenticated"),
            patch(
                "test_pr_merge_ready.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("test_pr_merge_ready.gh_graphql", return_value=_payload(base="feature/parent")),
        ):
            rc = main(["--pull-request", "42"])

        assert rc == 0
        assert json.loads(capsys.readouterr().out)["Tier"] == "STACKED"


class TestOnlyTheMergeStepIsGated:
    """STACKED replaces T1 and nothing else: repair tiers keep their meaning."""

    @pytest.mark.parametrize(
        ("merge_state", "tier"),
        [
            ("BEHIND", "BEHIND"),
            ("DIRTY", "DIRTY"),
            ("BLOCKED", "BLOCKED"),
            ("UNKNOWN", "UNSUPPORTED"),
        ],
    )
    def test_merge_state_tiers_win_over_stacked(self, merge_state, tier):
        result = _readiness(_payload(base="feature/parent", merge_state=merge_state))

        assert result["Tier"] == tier

    def test_a_stacked_pr_with_a_failed_required_check_is_t2(self):
        pr_data = _payload(base="feature/parent")
        contexts = pr_data["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"][
            "statusCheckRollup"
        ]["contexts"]["nodes"]
        contexts[0]["conclusion"] = "FAILURE"

        assert _readiness(pr_data)["Tier"] == "T2"

    def test_a_stacked_pr_with_an_unresolved_thread_is_t3(self):
        pr_data = _payload(base="feature/parent")
        pr_data["repository"]["pullRequest"]["reviewThreads"] = {
            "totalCount": 1,
            "nodes": [{"id": "t1", "isResolved": False}],
        }

        assert _readiness(pr_data)["Tier"] == "T3"

    def test_a_stacked_draft_is_skip(self):
        pr_data = _payload(base="feature/parent")
        pr_data["repository"]["pullRequest"]["isDraft"] = True

        assert _readiness(pr_data)["Tier"] == "SKIP"


class TestAnUnprovableBaseFailsClosed:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"base": None},
            {"base": ""},
            {"base": 7},
            {"default": None},
            {"default": ""},
            {"default": 7},
            {"default_ref": None},
            {"default_ref": {}},
            {"default_ref": {"name": None}},
        ],
    )
    def test_a_missing_or_malformed_name_is_never_t1(self, kwargs):
        result = _readiness(_payload(**kwargs))

        assert result["Tier"] == "STACKED"

    @pytest.mark.parametrize("repo_value", [None, "main", []])
    def test_a_missing_base_repository_is_never_t1(self, repo_value):
        pr_data = _payload()
        pr_data["repository"]["pullRequest"]["baseRepository"] = repo_value

        assert _readiness(pr_data)["Tier"] == "STACKED"

    def test_an_absent_key_is_never_t1(self):
        pr_data = _payload()
        del pr_data["repository"]["pullRequest"]["baseRefName"]
        del pr_data["repository"]["pullRequest"]["baseRepository"]

        result = _readiness(pr_data)

        assert result["Tier"] == "STACKED"
        assert result["BaseRef"] == ""
        assert result["DefaultBranch"] == ""

    def test_branch_names_compare_exactly(self):
        assert _readiness(_payload(base="Main"))["Tier"] == "STACKED"


class TestClassifyTierDirectly:
    @staticmethod
    def _ready(**overrides) -> dict:
        result = {
            "CanMerge": True,
            "IsDraft": False,
            "State": "OPEN",
            "MergeStateStatus": "CLEAN",
            "BaseRef": "main",
            "DefaultBranch": "main",
            "FailedRequiredChecks": [],
            "UndisposedNonRequiredFailures": [],
            "UnresolvedThreads": 0,
            "PendingRequiredChecks": [],
        }
        result.update(overrides)
        return result

    def test_matching_names_are_t1(self):
        assert classify_tier(self._ready()) == "T1"

    def test_differing_names_are_stacked(self):
        assert classify_tier(self._ready(BaseRef="release/1.0")) == "STACKED"

    def test_a_result_without_the_fields_is_never_t1(self):
        result = self._ready()
        del result["BaseRef"]
        del result["DefaultBranch"]

        assert classify_tier(result) == "STACKED"

    def test_can_merge_false_is_not_promoted_to_stacked(self):
        result = self._ready(BaseRef="feature/parent", CanMerge=False)

        assert classify_tier(result) == "T4"


class TestTheQueryAsksForTheBase:
    def test_query_requests_the_base_ref_and_default_branch(self):
        assert "baseRefName" in _mod._MERGE_READY_QUERY
        assert "defaultBranchRef" in _mod._MERGE_READY_QUERY

    def test_stacked_is_a_declared_tier(self):
        assert "STACKED" in _mod._TIER_ORDER
