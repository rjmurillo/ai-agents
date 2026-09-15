"""Tests for the dict[str, Any] | list[Any] rest_get narrowing (CodeRabbit,
PR #5787 review).

`GitHubClient.rest_get`'s return type widened to cover both a
single-resource endpoint (JSON object) and a list endpoint (top-level JSON
array). Two call sites that assume one specific shape now fail closed
(TypeError) instead of crashing on a missing dict method or silently
mis-processing a list as a dict, when the API returns the other shape.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.github_core.pull_request_targets import pull_request_targets
from scripts.github_core.workflow_runs import iter_paginated


class _FakeClient:
    def __init__(self, response: object) -> None:
        self._response = response

    def rest_get(self, endpoint: str) -> object:
        return self._response


class TestIterPaginatedRejectsNonDict:
    def test_dict_shaped_actions_response_yields_items(self):
        client = _FakeClient({"workflow_runs": [{"id": 1}, {"id": 2}]})
        result = list(iter_paginated(client, "actions/runs", "workflow_runs"))
        assert result == [{"id": 1}, {"id": 2}]

    def test_list_shaped_response_raises_type_error(self):
        """The Actions endpoints always wrap items in an object; a bare
        array here is a real API-contract break, not a shape this
        function accepts."""
        client = _FakeClient([{"id": 1}])
        with pytest.raises(TypeError, match="expected a JSON object"):
            list(iter_paginated(client, "actions/runs", "workflow_runs"))


class TestPullRequestTargetsRejectsNonDict:
    def test_dict_shaped_response_builds_target(self):
        client = MagicMock()
        client.rest_get.return_value = {
            "number": 1,
            "head": {"ref": "feature", "repo": {"full_name": "owner/repo"}},
        }
        result = pull_request_targets(client, "owner/repo", [1])
        assert len(result) == 1
        assert result[0].pr_number == 1

    def test_list_shaped_response_raises_type_error(self):
        """A single-PR-by-number endpoint always returns a JSON object; a
        bare array here means the API contract broke."""
        client = MagicMock()
        client.rest_get.return_value = [{"number": 1}]
        with pytest.raises(TypeError, match="expected a JSON object"):
            pull_request_targets(client, "owner/repo", [1])
