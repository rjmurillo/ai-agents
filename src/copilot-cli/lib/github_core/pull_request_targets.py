"""Discover the pull requests a bulk cancellation will enumerate runs for.

Issue #4835. Split out of ``scripts/bulk_cancel_guard.py`` so that file stays
under the 500-line taste ceiling.

Each pull request is resolved to a
:class:`~scripts.github_core.workflow_runs.PullRequestTarget` carrying its head
repository, which is what keeps two forks using one branch name from being
confused for each other. A payload that does not name its head repository is
refused rather than defaulted to the base repository: see
:func:`target_from_pull_request`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from .protocol import GitHubClient
from .workflow_runs import PAGE_SIZE, PullRequestTarget

__all__ = [
    "iter_paginated_list",
    "open_pull_request_targets",
    "pull_request_targets",
    "target_from_pull_request",
]

# Open PRs on this repository sit in the low hundreds; 50 pages of 100 is an
# order of magnitude of headroom and bounds a paging bug against a live API.
_MAX_LIST_PAGES = 50


def target_from_pull_request(payload: Mapping[str, Any]) -> PullRequestTarget:
    """Build a :class:`PullRequestTarget` from a pull-request payload.

    Raises:
        ValueError: when the number, head ref, or head repository is missing.
            The head repository is what keeps a fork pull request sharing a
            branch name from being attributed to this one, so a payload without
            it cannot be planned against safely and must not fall back to the
            base repository (see :class:`PullRequestTarget`).
    """
    number = payload.get("number")
    head = payload.get("head")
    ref = head.get("ref") if isinstance(head, Mapping) else None
    head_repo = head.get("repo") if isinstance(head, Mapping) else None
    full_name = head_repo.get("full_name") if isinstance(head_repo, Mapping) else None
    if not isinstance(number, int):
        raise ValueError(f"pull request payload has no number: {payload!r}")
    if not isinstance(ref, str) or not ref:
        raise ValueError(f"pull request #{number} has no head branch")
    if not isinstance(full_name, str) or not full_name:
        raise ValueError(
            f"pull request #{number} has no head repository, so its runs cannot "
            "be told apart from another fork's runs on the same branch name"
        )
    return PullRequestTarget(
        pr_number=number, branch=ref, head_repository=full_name
    )


def open_pull_request_targets(
    client: GitHubClient, repository: str, base: str
) -> list[PullRequestTarget]:
    """Build one target per open PR targeting ``base``.

    A list, not a branch-keyed mapping: two open pull requests from two
    different forks can use the same head branch name, and a mapping would drop
    one of them.
    """
    # Same reason as workflow_runs._query_value: a base ref carrying `&`, `?`,
    # `#`, or `+` would otherwise inject or corrupt query parameters and return
    # a different PR set than the operator named.
    endpoint = (
        f"repos/{quote(repository, safe='/')}/pulls"
        f"?state=open&base={quote(base, safe='')}"
    )
    return [
        target_from_pull_request(payload)
        for payload in iter_paginated_list(client, endpoint)
    ]


def iter_paginated_list(client: GitHubClient, endpoint: str) -> list[dict[str, Any]]:
    """Page a REST endpoint whose body is a bare JSON array.

    The Actions endpoints wrap their items in an object, so
    :func:`~scripts.github_core.workflow_runs.iter_paginated` reads a key. The
    pulls endpoint returns a top-level array instead, which needs this second
    walk. Both stop on the first short page.
    """
    separator = "&" if "?" in endpoint else "?"
    items: list[dict[str, Any]] = []
    for page in range(1, _MAX_LIST_PAGES + 1):
        body: Any = client.rest_get(f"{endpoint}{separator}per_page={PAGE_SIZE}&page={page}")
        if not isinstance(body, list) or not body:
            return items
        items.extend(entry for entry in body if isinstance(entry, dict))
        if len(body) < PAGE_SIZE:
            return items
    return items


def pull_request_targets(
    client: GitHubClient, repository: str, pr_numbers: Sequence[int]
) -> list[PullRequestTarget]:
    return [
        target_from_pull_request(
            client.rest_get(f"repos/{quote(repository, safe='/')}/pulls/{number}")
        )
        for number in pr_numbers
    ]
