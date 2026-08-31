"""Shared fake client and payload builders for the run-enumeration tests.

Split out of ``tests/ci/test_workflow_runs.py`` when the fork-identity cases
(issue #4835, Copilot review on PR #5357) pushed that file past the 500-line
taste ceiling. Plain helpers only; no pytest fixtures, so importing this module
never shadows a fixture name in a consumer.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote

from scripts.github_core.workflow_runs import PAGE_SIZE, PullRequestTarget

BASE_REPOSITORY = "o/r"
FORK_REPOSITORY = "forker/r"


class FakeClient:
    """Records reads and writes, answering from a canned response table."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.gets: list[str] = []
        self.posts: list[str] = []
        self.post_failures: dict[str, Exception] = {}

    def rest_get(self, endpoint: str) -> Any:
        self.gets.append(endpoint)
        if endpoint in self.responses:
            return self.responses[endpoint]
        return {}

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.posts.append(endpoint)
        failure = self.post_failures.get(endpoint)
        if failure is not None:
            raise failure
        return {}

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {}

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return {}

    def is_authenticated(self) -> bool:
        return True


def page_url(endpoint: str, page: int) -> str:
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}per_page={PAGE_SIZE}&page={page}"


def runs_url(repository: str, branch: str, status: str) -> str:
    """The branch-runs endpoint the module builds, with values percent-encoded.

    Spelled out here rather than reusing the module's private helpers so the
    encoding contract is asserted by the fixture rather than borrowed from the
    code under test.
    """
    return (
        f"repos/{quote(repository, safe='/')}/actions/runs"
        f"?branch={quote(branch, safe='')}&status={quote(status, safe='')}"
    )


def target(
    branch: str, pr_number: int, head_repository: str = BASE_REPOSITORY
) -> PullRequestTarget:
    """Build the pull-request target ``collect_runs_for_targets`` enumerates."""
    return PullRequestTarget(
        pr_number=pr_number, branch=branch, head_repository=head_repository
    )


def contents_endpoint(repository: str, path: str, ref: str) -> str:
    """The contents endpoint ``workflow_provenance`` reads a definition from.

    Spelled out here rather than borrowed from the module under test, so the
    URL shape is asserted by the fixture instead of by the code that builds it.
    """
    return (
        f"repos/{quote(repository, safe='/')}/contents/{quote(path, safe='/')}"
        f"?ref={quote(ref, safe='')}"
    )


def contents_payload(document: object) -> dict[str, Any]:
    """A contents response carrying ``document`` the way GitHub returns it."""
    encoded = base64.b64encode(
        json.dumps(document).encode("utf-8")
    ).decode("ascii")
    return {"encoding": "base64", "content": encoded}


def run_payload(
    run_id: int,
    *,
    name: str = "W",
    status: str = "queued",
    event: str = "synchronize",
    head_repository: str | None = BASE_REPOSITORY,
    path: str | None = None,
) -> dict[str, Any]:
    """One workflow-run payload in the shape the Actions list endpoint returns.

    ``head_repository`` carries the identity that tells this pull request's
    runs from another fork's runs on a branch of the same name. Passing None
    omits the field, which is the unattributable shape.

    ``path`` names the workflow file that produced the run, which is what the
    live provenance resolver fetches from the pull request's merge ref. Passing
    None omits it, which is the unresolvable shape.
    """
    payload: dict[str, Any] = {
        "id": run_id,
        "name": name,
        "event": event,
        "status": status,
    }
    if head_repository is not None:
        payload["head_repository"] = {"full_name": head_repository}
    if path is not None:
        payload["path"] = path
    return payload


