"""Authoritative merge-state reader for a single pull request (issue #4951).

Answers one question, "is PR #N merged", with three possible answers instead
of two:

- ``MERGED``: the remote said ``merged: true``.
- ``UNMERGED``: the remote said ``merged: false`` (open, or closed unmerged).
- ``PROBE_FAILED``: the remote said nothing usable (transport error, auth
  failure, malformed payload). Evidence was not obtained, so no merge-state
  claim can be made.

``NOT_FOUND`` is a fourth, still-verified answer: the repository responded and
reported no such pull request.

Collapsing ``PROBE_FAILED`` into ``UNMERGED`` is the defect this module was
written to remove. ``close_issue.py::_pr_is_merged`` returned ``False`` for
every nonzero ``gh api`` exit and every JSON decode failure, and its caller
turned that missing evidence into the factual sentence "cited PR #N is not
merged". On 2026-08-13 that aborted the close of issue #4858 by reporting PR
#4729 (merged 2026-08-07) and PR #3076 (merged 2026-07-16) as unmerged.

Canonical query provenance
--------------------------
``PR_MERGE_STATE_QUERY`` below is the query from
``.claude/skills/github/scripts/pr/test_pr_merged.py::_QUERY`` at commit
bc179ad3a, copied character-for-character:

    query($owner: String!, $repo: String!, $prNumber: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          state
          merged
          mergedAt
          mergedBy {
            login
          }
        }
      }
    }

That script now calls :func:`read_pr_merge_state` instead of holding its own
copy, so the GraphQL contract has exactly one home. GraphQL is used rather than
the REST ``repos/{owner}/{repo}/pulls/{number}`` endpoint because
``test_pr_merged.py`` is the reader the 2026-08-13 incident used to prove the
REST probe wrong (issue #4951, "Reuse the shared PR state reader or the same
remote contract as test_pr_merged.py").

Stricter/looser/different than canonical
----------------------------------------
- Stricter than ``test_pr_merged.py`` was: that script read
  ``pr.get("merged", False)``, which reports a payload with no ``merged`` key
  as not merged. Here a non-boolean ``merged`` is ``PROBE_FAILED``. A missing
  field is missing evidence, not a negative answer.
- Different from ``github_core.api.classify_gh_failure_text``: that function's
  fallback bucket is ``INVALID_CREDENTIALS`` because it classifies the output
  of an auth preflight that already failed. Applying it to an arbitrary API
  error would call every unrecognized failure a credential fault. This module
  uses :func:`github_core.api.is_auth_failure_text`, which requires an explicit
  marker, and maps everything else to exit 3.
- No exit code is assigned to ``MERGED``, ``UNMERGED``, or ``NOT_FOUND``.
  Callers disagree on those by design: ``test_pr_merged.py`` exits 2 on
  ``NOT_FOUND`` (its documented contract), while ``close_issue.py`` treats it
  as a failed claim (exit 1). ``PrMergeState.exit_code`` is populated only for
  ``PROBE_FAILED``, where ADR-035 fixes the answer at 3 (external) or 4 (auth).

Not to be confused with ``scripts/ci/check_pr_merge_state.py``. That script
asks whether an open PR for a pushed branch *can* merge (GitHub's
``mergeStateStatus``, DIRTY and friends). This module asks whether a PR
*was* merged. Similar names, different questions.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum

from .api import (
    gh_graphql,
    is_auth_failure_text,
    sanitize_failure_detail,
)

PR_MERGE_STATE_QUERY = """\
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      state
      merged
      mergedAt
      mergedBy {
        login
      }
    }
  }
}"""

# Probe details reach error envelopes and operator terminals. Cap the length so
# a multi-kilobyte GraphQL error body cannot swamp the message that explains it.
_DETAIL_LIMIT = 200


class PrMergeStatus(Enum):
    """What the remote actually told us about a pull request's merge state."""

    MERGED = "merged"
    UNMERGED = "unmerged"
    NOT_FOUND = "not_found"
    PROBE_FAILED = "probe_failed"


@dataclass(frozen=True)
class PrMergeState:
    """One pull request's merge state, or the reason we could not read it.

    Attributes:
        owner: Repository owner queried.
        repo: Repository name queried.
        number: Pull request number queried.
        status: The tri-state answer plus ``NOT_FOUND``.
        state: GraphQL ``PullRequest.state`` (``OPEN``/``CLOSED``/``MERGED``),
            or None when the probe returned no pull request.
        merged_at: GraphQL ``mergedAt`` timestamp, or None.
        merged_by: Login from GraphQL ``mergedBy``, or None.
        detail: Sanitized failure reason. Non-empty only for ``PROBE_FAILED``.
        exit_code: ADR-035 code for ``PROBE_FAILED`` (3 external, 4 auth).
            Zero for every verified status; those callers choose their own.
    """

    owner: str
    repo: str
    number: int
    status: PrMergeStatus
    state: str | None = None
    merged_at: str | None = None
    merged_by: str | None = None
    detail: str = ""
    exit_code: int = 0

    @property
    def is_merged(self) -> bool:
        """True only when the remote confirmed the merge."""
        return self.status is PrMergeStatus.MERGED

    @property
    def is_verified(self) -> bool:
        """True when the remote answered, whatever the answer was."""
        return self.status is not PrMergeStatus.PROBE_FAILED


def _probe_failed(
    owner: str, repo: str, number: int, detail: object
) -> PrMergeState:
    """Build a PROBE_FAILED state, mapping the detail to exit 3 or 4."""
    text = sanitize_failure_detail(detail, _DETAIL_LIMIT)
    return PrMergeState(
        owner=owner,
        repo=repo,
        number=number,
        status=PrMergeStatus.PROBE_FAILED,
        detail=text,
        exit_code=4 if is_auth_failure_text(text) else 3,
    )


def _merged_by_login(pull_request: dict) -> str | None:
    """Return the ``mergedBy.login`` value, tolerating a null ``mergedBy``."""
    merged_by = pull_request.get("mergedBy")
    if not isinstance(merged_by, dict):
        return None
    login = merged_by.get("login")
    return login if isinstance(login, str) else None


def _classify(
    owner: str, repo: str, number: int, data: object
) -> PrMergeState:
    """Turn a GraphQL ``data`` payload into a PrMergeState.

    Every shape that is not a definite answer becomes ``PROBE_FAILED``. A null
    ``pullRequest`` under a present ``repository`` is the one documented
    "the remote answered, and the answer is no such PR" shape, so it alone
    becomes ``NOT_FOUND``.
    """
    repository = data.get("repository") if isinstance(data, dict) else None
    if not isinstance(repository, dict):
        return _probe_failed(
            owner, repo, number, "GraphQL response carried no repository object"
        )
    if "pullRequest" not in repository:
        return _probe_failed(
            owner, repo, number, "GraphQL response carried no pullRequest field"
        )

    pull_request = repository["pullRequest"]
    if pull_request is None:
        return PrMergeState(
            owner=owner, repo=repo, number=number, status=PrMergeStatus.NOT_FOUND
        )
    if not isinstance(pull_request, dict):
        return _probe_failed(
            owner, repo, number, "GraphQL pullRequest was not an object"
        )

    merged = pull_request.get("merged")
    if merged is not True and merged is not False:
        return _probe_failed(
            owner, repo, number, "GraphQL pullRequest.merged was not a boolean"
        )

    pr_state = pull_request.get("state")
    merged_at = pull_request.get("mergedAt")
    return PrMergeState(
        owner=owner,
        repo=repo,
        number=number,
        status=PrMergeStatus.MERGED if merged else PrMergeStatus.UNMERGED,
        state=pr_state if isinstance(pr_state, str) else None,
        merged_at=merged_at if isinstance(merged_at, str) else None,
        merged_by=_merged_by_login(pull_request),
    )


def read_pr_merge_state(owner: str, repo: str, number: int) -> PrMergeState:
    """Read PR #``number``'s merge state without ever guessing.

    Args:
        owner: Repository owner.
        repo: Repository name.
        number: Pull request number.

    Returns:
        A :class:`PrMergeState`. Never raises for a remote failure: a transport
        error, an auth failure, or an unusable payload all return
        ``PROBE_FAILED`` with a sanitized ``detail`` and an ADR-035
        ``exit_code``, so callers cannot silently read a failed probe as
        "not merged".

    ``subprocess.TimeoutExpired`` is caught alongside ``RuntimeError`` because
    ``gh_graphql`` runs ``subprocess.run(..., timeout=30)``, and that exception
    is not a ``RuntimeError``. Uncaught, it would end the process with Python's
    default exit 1, which ADR-035 reserves for a logic failure. A probe that
    ran out of time would then be indistinguishable from a verified bad claim,
    which is the confusion this module exists to remove.
    """
    try:
        data = gh_graphql(
            PR_MERGE_STATE_QUERY,
            {"owner": owner, "repo": repo, "prNumber": number},
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return _probe_failed(owner, repo, number, exc)
    return _classify(owner, repo, number, data)
