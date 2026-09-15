"""GitHubClient protocol: transport-layer abstraction for testable API access."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GitHubClient(Protocol):
    """PEP 544 structural subtyping protocol for GitHub API transport.

    Implementations wrap a specific transport (gh CLI, httpx, fake/stub)
    while consumers depend only on this interface.
    """

    def rest_get(self, endpoint: str) -> dict[str, Any] | list[Any]:
        """GET *endpoint* and return the parsed JSON body.

        A union, not a bare `dict[str, Any]` (CodeRabbit, PR #5787
        review): a single-resource endpoint (e.g. `pulls/{number}`)
        returns a JSON object, but a list endpoint (e.g. `pulls`, no
        number) returns a top-level JSON array. Declaring only the dict
        half masked the mismatch behind implementers' own `Any`
        annotations at call sites (`pull_request_targets.
        iter_paginated_list`) instead of letting mypy see it.
        """
        ...

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    def is_authenticated(self) -> bool: ...
