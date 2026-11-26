"""Focused GitHub Core contract cases."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core import (
    FetchStatus,
    count_unresolved_threads,
    filter_unresolved_threads,
    gh_graphql,
)
from tests.github_core_test_helpers import _completed


class TestGhGraphQL:
    def test_simple_query(self):
        response = json.dumps({"data": {"viewer": {"login": "testuser"}}})
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            result = gh_graphql("query { viewer { login } }")
        assert result == {"viewer": {"login": "testuser"}}

    def test_with_string_variables(self):
        response = json.dumps({"data": {"repository": {"name": "ai-agents"}}})
        with patch("subprocess.run", return_value=_completed(stdout=response)) as mock:
            gh_graphql("query($owner: String!) { ... }", {"owner": "rjmurillo"})
        cmd = mock.call_args[0][0]
        assert "-f" in cmd
        assert "owner=rjmurillo" in cmd

    def test_with_int_variables(self):
        response = json.dumps({"data": {}})
        with patch("subprocess.run", return_value=_completed(stdout=response)) as mock:
            gh_graphql("query($num: Int!) { ... }", {"num": 42})
        cmd = mock.call_args[0][0]
        assert "-F" in cmd
        assert "num=42" in cmd

    def test_transport_error_raises(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="network error")):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                gh_graphql("query { viewer { login } }")

    def test_graphql_level_error_raises(self):
        response = json.dumps({"data": None, "errors": [{"message": "Not found"}]})
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            with pytest.raises(RuntimeError, match="GraphQL errors.*Not found"):
                gh_graphql("query { ... }")

    def test_invalid_json_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="Failed to parse"):
                gh_graphql("query { ... }")

    def test_retries_transient_504_then_succeeds(self):
        """A transient HTTP 504 followed by success returns data (issue #2631)."""
        ok = json.dumps({"data": {"viewer": {"login": "u"}}})
        responses = [
            _completed(rc=1, stderr="gh: We couldn't respond in time. (HTTP 504)"),
            _completed(stdout=ok),
        ]
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", side_effect=responses) as run_mock,
        ):
            result = gh_graphql("query { viewer { login } }")
        assert result == {"viewer": {"login": "u"}}
        assert run_mock.call_count == 2
        assert sleep_mock.call_count == 1

    def test_retries_exhausted_on_persistent_504_raises(self):
        """Three consecutive 504s exhaust the bounded retry and raise (issue #2631)."""
        resp = _completed(rc=1, stderr="gh: timeout (HTTP 504)")
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", return_value=resp) as run_mock,
        ):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                gh_graphql("query { viewer { login } }")
        assert run_mock.call_count == 3
        assert sleep_mock.call_count == 2

    def test_retries_on_502_503_500_and_429(self):
        """Each transient 5xx and 429 retries then succeeds (issue #2631)."""
        ok = json.dumps({"data": {}})
        for code in ("500", "502", "503", "429"):
            responses = [
                _completed(rc=1, stderr=f"server error (HTTP {code})"),
                _completed(stdout=ok),
            ]
            with (
                patch("scripts.github_core.api.time.sleep"),
                patch("subprocess.run", side_effect=responses) as run_mock,
            ):
                gh_graphql("query { x }")
            assert run_mock.call_count == 2, code

    def test_permanent_404_does_not_retry(self):
        """A permanent client error (404, not 5xx/429) fails fast without retry."""
        resp = _completed(rc=1, stderr="gh: Not Found (HTTP 404)")
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", return_value=resp) as run_mock,
        ):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                gh_graphql("query { x }")
        assert run_mock.call_count == 1
        assert sleep_mock.call_count == 0

    def test_graphql_level_error_does_not_retry(self):
        """A GraphQL-level error (HTTP 200 with errors) is permanent, no retry."""
        resp = _completed(stdout=json.dumps({"data": None, "errors": [{"message": "Bad"}]}))
        with (
            patch("scripts.github_core.api.time.sleep") as sleep_mock,
            patch("subprocess.run", return_value=resp) as run_mock,
        ):
            with pytest.raises(RuntimeError, match="GraphQL errors"):
                gh_graphql("query { x }")
        assert run_mock.call_count == 1
        assert sleep_mock.call_count == 0


class TestFetchStatus:
    def test_str_enum_values(self):
        assert FetchStatus.OK == "ok"
        assert FetchStatus.TRANSPORT_ERROR == "transport_error"
        assert FetchStatus.STRUCTURAL_MISSING == "structural_missing"

    @pytest.mark.parametrize(
        ("member", "rendered"),
        [
            (FetchStatus.OK, "ok"),
            (FetchStatus.TRANSPORT_ERROR, "transport_error"),
            (FetchStatus.STRUCTURAL_MISSING, "structural_missing"),
        ],
    )
    def test_rendering_a_member_yields_its_value(self, member, rendered):
        """Equality is not the contract; rendering is, and they came apart.

        Dropping `enum.StrEnum` for `str, Enum` at the 3.10 portability floor
        keeps every equality comparison working and silently changes
        `str(FetchStatus.OK)` from "ok" to "FetchStatus.OK", because StrEnum
        inherits `str.__str__` and a plain `str, Enum` takes `Enum.__str__`.
        The three assertions above passed through that whole change. Every log
        line, f-string, and serialized field carrying this value changed shape,
        and FetchStatus is exported from `github_core`, so the blast radius is
        outside this module (Copilot review on PR #5509).
        """
        assert str(member) == rendered
        assert f"{member}" == rendered
        assert format(member) == rendered
        assert "{}".format(member) == rendered  # noqa: UP032

    def test_typo_raises_attribute_error(self):
        """Typo on a StrEnum member is a fail-fast attribute error,
        unlike a bare-string sentinel which would silently miss.
        """
        with pytest.raises(AttributeError):
            _ = FetchStatus.OK_TYPO


class TestCountUnresolvedThreads:
    def test_empty_list(self):
        assert count_unresolved_threads([]) == 0

    def test_all_resolved(self):
        nodes = [{"isResolved": True}, {"isResolved": True}]
        assert count_unresolved_threads(nodes) == 0

    def test_all_unresolved(self):
        nodes = [{"isResolved": False}, {"isResolved": False}]
        assert count_unresolved_threads(nodes) == 2

    def test_mixed(self):
        nodes = [
            {"isResolved": True},
            {"isResolved": False},
            {"isResolved": False},
        ]
        assert count_unresolved_threads(nodes) == 2

    def test_missing_is_resolved_defaults_to_resolved(self):
        """A malformed thread without isResolved defaults to resolved
        (treated as not unresolved). Prevents a missing field from
        silently inflating the unresolved count.
        """
        nodes = [{}, {"id": "x"}]
        assert count_unresolved_threads(nodes) == 0

    def test_explicit_null_is_resolved_defaults_to_resolved(self):
        """An explicit null isResolved from the GraphQL payload is treated the
        same as a missing field (resolved), so it is not counted as unresolved.
        """
        nodes = [{"isResolved": None}, {"id": "x", "isResolved": None}]
        assert count_unresolved_threads(nodes) == 0


class TestFilterUnresolvedThreads:
    def test_returns_only_unresolved(self):
        nodes = [
            {"id": "a", "isResolved": True},
            {"id": "b", "isResolved": False},
            {"id": "c", "isResolved": False},
        ]
        result = filter_unresolved_threads(nodes)
        assert [t["id"] for t in result] == ["b", "c"]

    def test_count_and_filter_agree(self):
        """The count helper and filter helper share the rule, so
        ``count == len(filter)`` for any input. This locks the DRY
        invariant in a test.
        """
        nodes = [
            {"isResolved": True},
            {"isResolved": False},
            {},
            {"isResolved": False},
            {"isResolved": None},
        ]
        assert count_unresolved_threads(nodes) == len(filter_unresolved_threads(nodes))
