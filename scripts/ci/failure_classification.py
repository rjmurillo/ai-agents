"""Classify PR-fetch failures and produce structured diagnostics.

Extracted from ``build_ai_review_context.py`` (issue #4597) so failure
classification is a cohesive, independently testable seam.

The two compiled patterns and the ``classify_pr_fetch_failure`` function
were previously inlined as ``FORK_PERMISSION_SIGNAL``,
``RATE_LIMIT_SIGNAL``, and ``_pr_fetch_failure_context``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Signal patterns
# ---------------------------------------------------------------------------

FORK_PERMISSION_SIGNAL = re.compile(
    r"HTTP 40[34]|not accessible|must have admin rights|Could not resolve to a PullRequest",
    re.IGNORECASE,
)
"""REST/GraphQL responses that *may* indicate a fork-permission problem."""

RATE_LIMIT_SIGNAL = re.compile(
    r"rate limit|secondary rate|abuse detection",
    re.IGNORECASE,
)
"""Disambiguator: a REST 403 caused by rate limiting, not permissions.

A REST rate-limit refusal arrives as ``HTTP 403: API rate limit exceeded …``,
which ``FORK_PERMISSION_SIGNAL`` matches on the status alone.  Suppressing the
hint on this signature keeps the #4333 misdiagnosis from returning through the
REST transport after it was fixed for GraphQL.
"""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FailureClassification:
    """Structured result of classifying a PR-fetch failure detail string.

    Attributes:
        detail: The (already-redacted) detail string that was classified.
        hint: An actionable hint appended to the warning, or empty.
        warning: The full ``::warning::`` line emitted to stdout.
        context_text: The ``INFRASTRUCTURE_FAILURE:`` payload for the
            ``ReviewContext.text`` field.
    """

    detail: str
    hint: str
    warning: str
    context_text: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_FORK_HINT = (
    " The GH_TOKEN may lack permissions for first-time contributor PRs from forks."
)


def classify_pr_fetch_failure(
    pr_number: str,
    detail: str,
) -> FailureClassification:
    """Classify *detail* and return a ``FailureClassification``.

    Fail closed: the observed error is always surfaced verbatim.
    ``REQ-008-05`` (issue #2818) keeps the ``DID_NOT_RUN`` behavior.
    Issue #4333 is why the fork-permission hint is conditional: an
    exhausted GraphQL quota was reported as a token permission problem.
    The REST form carries an HTTP status, so the hint also needs the
    rate-limit signature to lose.

    Parameters:
        pr_number: The PR number string (e.g. ``"4637"``).
        detail: The *already-redacted* error detail.  The caller is
            responsible for redaction; this function never mutates secrets.
    """
    detail = detail.strip() or "GitHub API returned no diagnostic output"
    hint = (
        _FORK_HINT
        if FORK_PERMISSION_SIGNAL.search(detail)
        and not RATE_LIMIT_SIGNAL.search(detail)
        else ""
    )
    warning = f"::warning::Could not fetch PR #{pr_number}: {detail}{hint}"
    context_text = (
        f"INFRASTRUCTURE_FAILURE: Could not fetch PR #{pr_number}: {detail}{hint}"
    )
    return FailureClassification(
        detail=detail,
        hint=hint,
        warning=warning,
        context_text=context_text,
    )
