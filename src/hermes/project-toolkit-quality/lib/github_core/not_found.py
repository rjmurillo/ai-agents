"""Classifier for gh output that reports a missing pull request (issue #6163).

gh words a missing PR two ways, depending on the transport:

- REST and ``gh pr view`` report ``Not Found (HTTP 404)`` or ``not found``.
- GraphQL reports ``Could not resolve to a PullRequest with the number of N``.

Each pr script used to keep its own copy of that text match, and the copies
disagreed: ``close_pr.py`` and ``get_pr_context.py`` matched only ``not found``,
so a GraphQL-worded miss exited 3 instead of 2. ``check_pr_live_state.py``
matched the bare prefix ``Could not resolve``, which also fires on a network
fault such as ``Could not resolve host`` and reported a transport failure as a
missing PR. This module is the one place the marker list lives.
"""

from __future__ import annotations

_PR_NOT_FOUND_MARKERS = (
    "not found",
    "could not resolve to a pullrequest",
)


def is_pr_not_found(text: str | None) -> bool:
    """Return True when gh output says the pull request does not exist.

    Matching is case-insensitive. ``None`` and empty text return False so a
    caller can pass ``stderr or stdout`` without a guard. ``Could not resolve
    host`` (a transport fault) and ``Could not resolve to a Repository`` (a
    wrong owner or repo) do not match: only a missing PR does.
    """
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _PR_NOT_FOUND_MARKERS)
