"""Canonical: scripts/github_core/protocol.py. Sync via scripts/sync_plugin_lib.py."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GitHubClient(Protocol):
    """PEP 544 structural subtyping protocol for GitHub API transport.

    Implementations wrap a specific transport (gh CLI, httpx, fake/stub)
    while consumers depend only on this interface.
    """

    def rest_get(self, endpoint: str) -> dict[str, Any]: ...

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    def is_authenticated(self) -> bool: ...
