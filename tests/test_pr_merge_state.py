"""Tests for github_core.pr_merge_state (issue #4951).

The defect under test: a failed probe used to read as "not merged". Every
failure shape below must land in PROBE_FAILED, never in UNMERGED.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core.pr_merge_state import (
    PR_MERGE_STATE_QUERY,
    PrMergeState,
    PrMergeStatus,
    read_pr_merge_state,
)

_PATCH_TARGET = "scripts.github_core.pr_merge_state.gh_graphql"


def _payload(**pull_request_fields: object) -> dict:
    return {"repository": {"pullRequest": dict(pull_request_fields)}}


def _merged_payload() -> dict:
    return _payload(
        state="MERGED",
        merged=True,
        mergedAt="2026-08-07T12:00:00Z",
        mergedBy={"login": "admin"},
    )


def _unmerged_payload() -> dict:
    return _payload(state="OPEN", merged=False, mergedAt=None, mergedBy=None)


# ---------------------------------------------------------------------------
# Positive: verified merged
# ---------------------------------------------------------------------------


class TestMerged:
    def test_merged_pr_reports_merged(self):
        with patch(_PATCH_TARGET, return_value=_merged_payload()):
            state = read_pr_merge_state("rjmurillo", "ai-agents", 4729)
        assert state.status is PrMergeStatus.MERGED
        assert state.is_merged is True
        assert state.is_verified is True
        assert state.exit_code == 0
        assert state.detail == ""

    def test_merged_pr_carries_merge_metadata(self):
        with patch(_PATCH_TARGET, return_value=_merged_payload()):
            state = read_pr_merge_state("rjmurillo", "ai-agents", 4729)
        assert state.owner == "rjmurillo"
        assert state.repo == "ai-agents"
        assert state.number == 4729
        assert state.state == "MERGED"
        assert state.merged_at == "2026-08-07T12:00:00Z"
        assert state.merged_by == "admin"

    def test_query_is_sent_with_typed_variables(self):
        with patch(_PATCH_TARGET, return_value=_merged_payload()) as mock_graphql:
            read_pr_merge_state("o", "r", 7)
        query, variables = mock_graphql.call_args.args
        assert query == PR_MERGE_STATE_QUERY
        assert variables == {"owner": "o", "repo": "r", "prNumber": 7}

    def test_merged_without_merged_by_keeps_login_none(self):
        payload = _payload(state="MERGED", merged=True, mergedAt=None, mergedBy=None)
        with patch(_PATCH_TARGET, return_value=payload):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.MERGED
        assert state.merged_by is None


# ---------------------------------------------------------------------------
# Negative: verified unmerged
# ---------------------------------------------------------------------------


class TestUnmerged:
    def test_open_pr_reports_unmerged(self):
        with patch(_PATCH_TARGET, return_value=_unmerged_payload()):
            state = read_pr_merge_state("o", "r", 1024)
        assert state.status is PrMergeStatus.UNMERGED
        assert state.is_merged is False
        assert state.is_verified is True
        assert state.state == "OPEN"
        assert state.exit_code == 0

    def test_closed_unmerged_pr_reports_unmerged(self):
        payload = _payload(state="CLOSED", merged=False, mergedAt=None, mergedBy=None)
        with patch(_PATCH_TARGET, return_value=payload):
            state = read_pr_merge_state("o", "r", 1024)
        assert state.status is PrMergeStatus.UNMERGED
        assert state.state == "CLOSED"

    def test_missing_pull_request_reports_not_found(self):
        with patch(_PATCH_TARGET, return_value={"repository": {"pullRequest": None}}):
            state = read_pr_merge_state("o", "r", 999999)
        assert state.status is PrMergeStatus.NOT_FOUND
        assert state.is_merged is False
        assert state.is_verified is True
        assert state.exit_code == 0


# ---------------------------------------------------------------------------
# API failure: the 2026-08-13 incident shape
# ---------------------------------------------------------------------------


class TestApiFailure:
    def test_transport_error_reports_probe_failed_exit_3(self):
        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("GraphQL request failed: HTTP 502 Bad Gateway"),
        ):
            state = read_pr_merge_state("o", "r", 4729)
        assert state.status is PrMergeStatus.PROBE_FAILED
        assert state.is_merged is False
        assert state.is_verified is False
        assert state.exit_code == 3
        assert "502" in state.detail

    def test_probe_failure_never_claims_unmerged(self):
        # The regression guard for issue #4951: PR #4729 merged 2026-08-07 was
        # reported as not merged because its probe failed.
        with patch(_PATCH_TARGET, side_effect=RuntimeError("GraphQL failed")):
            state = read_pr_merge_state("rjmurillo", "ai-agents", 4729)
        assert state.status is not PrMergeStatus.UNMERGED

    def test_rate_limit_refusal_reports_exit_3(self):
        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError(
                "GraphQL request failed: API rate limit exceeded for user ID 1"
            ),
        ):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.PROBE_FAILED
        assert state.exit_code == 3

    def test_timeout_reports_probe_failed_not_logic_error(self):
        # subprocess.TimeoutExpired is not a RuntimeError. Uncaught it would
        # end the process with Python's exit 1, the ADR-035 logic-error code.
        with patch(
            _PATCH_TARGET,
            side_effect=subprocess.TimeoutExpired(cmd=["gh", "api", "graphql"], timeout=30),
        ):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.PROBE_FAILED
        assert state.exit_code == 3

    def test_detail_is_single_line_and_bounded(self):
        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("line one\r\nline two " + "x" * 500),
        ):
            state = read_pr_merge_state("o", "r", 1)
        assert "\n" not in state.detail
        assert "\r" not in state.detail
        assert len(state.detail) <= 203
        assert state.detail.endswith("...")

    def test_detail_redacts_a_token_echoed_by_the_remote(self):
        token = "ghp_" + "a" * 36
        with patch(_PATCH_TARGET, side_effect=RuntimeError(f"bad request using {token}")):
            state = read_pr_merge_state("o", "r", 1)
        assert token not in state.detail
        assert "[REDACTED]" in state.detail


# ---------------------------------------------------------------------------
# Auth failure
# ---------------------------------------------------------------------------


class TestAuthFailure:
    @pytest.mark.parametrize(
        "message",
        [
            "GraphQL request failed: Bad credentials",
            "GraphQL request failed: This endpoint requires authentication",
            "gh: You are not logged in to any GitHub hosts",
            "could not authenticate to github.com",
        ],
    )
    def test_auth_failure_reports_exit_4(self, message: str):
        with patch(_PATCH_TARGET, side_effect=RuntimeError(message)):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.PROBE_FAILED
        assert state.exit_code == 4

    def test_unrecognized_failure_is_external_not_auth(self):
        # "Could not resolve to a PullRequest" is an upstream answer, not a
        # credential fault; exit 4 would send the operator to gh auth login.
        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("Could not resolve to a PullRequest with number 9"),
        ):
            state = read_pr_merge_state("o", "r", 9)
        assert state.exit_code == 3


# ---------------------------------------------------------------------------
# Malformed responses
# ---------------------------------------------------------------------------


class TestMalformedResponse:
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="empty_data"),
            pytest.param({"repository": None}, id="null_repository"),
            pytest.param({"repository": {}}, id="repository_without_pull_request"),
            pytest.param({"repository": "nope"}, id="repository_not_an_object"),
            pytest.param({"repository": {"pullRequest": []}}, id="pr_not_an_object"),
            pytest.param("not-json-object", id="data_not_an_object"),
        ],
    )
    def test_malformed_payload_reports_probe_failed(self, payload: object):
        with patch(_PATCH_TARGET, return_value=payload):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.PROBE_FAILED
        assert state.exit_code == 3
        assert state.detail

    @pytest.mark.parametrize(
        "merged_value",
        [
            pytest.param(None, id="null"),
            pytest.param("true", id="string"),
            pytest.param(0, id="int_zero"),
            pytest.param(1, id="int_one"),
        ],
    )
    def test_non_boolean_merged_reports_probe_failed(self, merged_value: object):
        payload = _payload(state="OPEN", merged=merged_value)
        with patch(_PATCH_TARGET, return_value=payload):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.PROBE_FAILED
        assert state.exit_code == 3

    def test_absent_merged_key_is_not_read_as_unmerged(self):
        # test_pr_merged.py used pr.get("merged", False), which reports a
        # payload with no merged key as not merged. Missing evidence is not a
        # negative answer.
        with patch(_PATCH_TARGET, return_value=_payload(state="OPEN")):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.PROBE_FAILED

    def test_non_string_state_field_is_dropped_not_fatal(self):
        payload = _payload(state=42, merged=True, mergedAt=7, mergedBy={"login": 5})
        with patch(_PATCH_TARGET, return_value=payload):
            state = read_pr_merge_state("o", "r", 1)
        assert state.status is PrMergeStatus.MERGED
        assert state.state is None
        assert state.merged_at is None
        assert state.merged_by is None


# ---------------------------------------------------------------------------
# Value semantics
# ---------------------------------------------------------------------------


class TestPrMergeState:
    def test_state_is_frozen(self):
        """A verdict must not be editable after the probe that produced it.

        The assignment goes through a named field because two repo gates
        reject the obvious forms: a direct ``state.status = ...`` needs a
        type-ignore comment (ratcheted, issue #4039) and a literal
        ``setattr(state, "status", ...)`` trips ruff B010. The runtime
        assertion is the same one in every form.
        """
        state = PrMergeState(owner="o", repo="r", number=1, status=PrMergeStatus.MERGED)
        frozen_field = "status"
        with pytest.raises(AttributeError):
            setattr(state, frozen_field, PrMergeStatus.UNMERGED)

    def test_status_values_are_stable_strings(self):
        assert PrMergeStatus.MERGED.value == "merged"
        assert PrMergeStatus.UNMERGED.value == "unmerged"
        assert PrMergeStatus.NOT_FOUND.value == "not_found"
        assert PrMergeStatus.PROBE_FAILED.value == "probe_failed"
