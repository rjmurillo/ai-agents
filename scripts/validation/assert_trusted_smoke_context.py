#!/usr/bin/env python3
"""Gate the authenticated CLI smoke to a trusted execution context (issue #2231 item 3, REQ-047).

The CLI smoke installs the real Copilot/Claude CLIs and runs a hook end to end.
That needs auth secrets, so the run MUST NOT execute attacker-controlled code
with those secrets in scope. Per ``.claude/rules/security.md`` and the issue-3
requirement, this script is the trusted-context gate. Per ADR-006 the decision
lives here, not in workflow YAML.

The smoke workflow triggers on ``pull_request`` and ``workflow_dispatch``.
GitHub withholds secrets from fork pull requests, but this gate re-checks the
event, repository, and head repository so a fork PR fails closed with a named
reason instead of a confusing missing-credential failure. It fails closed:
anything it cannot positively confirm is untrusted.

Authorized when ALL hold:
- ``--event-name`` is ``pull_request`` or ``workflow_dispatch``. ``schedule``
  is no longer a trigger (REQ-047 removed the nightly).
- ``--repository`` equals the expected trusted repo (default
  ``rjmurillo/ai-agents``), so a fork running this workflow does not match.
- For ``pull_request``: ``--head-repository`` equals ``--repository``, so a PR
  whose head lives in a fork is denied. A missing or blank head repository is
  denied too (a deleted fork reports an empty value).
- For ``workflow_dispatch``: ``--ref`` equals the expected trusted ref (default
  ``refs/heads/main``), so a manual dispatch from another branch cannot run
  code with smoke secrets. A pull request ref (``refs/pull/N/merge``) is not
  compared to the default branch; the head-repository rule governs it.

Prints ``true`` or ``false`` to stdout for the workflow to branch on.

Exit codes (per AGENTS.md / ADR-035):
- 0: decision made (stdout is ``true`` or ``false``).
- 2: usage error (missing or malformed arguments).
"""

from __future__ import annotations

import argparse
import sys

EXIT_OK = 0
EXIT_USAGE = 2

_PULL_REQUEST = "pull_request"
_WORKFLOW_DISPATCH = "workflow_dispatch"
_TRUSTED_EVENTS = frozenset({_PULL_REQUEST, _WORKFLOW_DISPATCH})
_DEFAULT_TRUSTED_REPO = "rjmurillo/ai-agents"
_DEFAULT_TRUSTED_REF = "refs/heads/main"


def is_trusted(
    event_name: str,
    repository: str,
    expected_repo: str,
    ref: str = _DEFAULT_TRUSTED_REF,
    expected_ref: str = _DEFAULT_TRUSTED_REF,
    head_repository: str | None = None,
) -> tuple[bool, str]:
    """Return ``(trusted, reason)`` for the given execution context.

    Fail-closed: an unrecognized event, a non-matching repository, a fork
    pull request, or a dispatch from a non-default ref is untrusted.
    """
    if event_name not in _TRUSTED_EVENTS:
        allowed = ", ".join(sorted(_TRUSTED_EVENTS))
        return (False, f"event is not a trusted trigger (allowed: {allowed})")
    if repository.casefold() != expected_repo.casefold():
        return (False, "repository is not the trusted repo")
    if event_name == _PULL_REQUEST:
        return _check_pull_request_head(repository, head_repository)
    if ref != expected_ref:
        return (False, "ref is not the trusted ref")
    return (True, "trusted context: approved event, repo, and ref")


def _check_pull_request_head(repository: str, head_repository: str | None) -> tuple[bool, str]:
    """Allow a pull request only when its head lives in the base repository."""
    head = (head_repository or "").strip()
    if not head:
        return (False, "pull request head repository is missing (deleted fork?)")
    if head.casefold() != repository.casefold():
        return (False, "pull request head is a fork of the trusted repo")
    return (True, "trusted context: approved event, repo, and same-repo head")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate the authenticated CLI smoke to a trusted context (issue #2231 item 3).",
    )
    parser.add_argument(
        "--event-name",
        required=True,
        help="The github.event_name of the triggering event.",
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="The github.repository the workflow is running in (owner/name).",
    )
    parser.add_argument(
        "--ref",
        required=True,
        help="The github.ref the workflow is running from.",
    )
    parser.add_argument(
        "--head-repository",
        default=None,
        help="The pull request head repository (owner/name). Required for pull_request.",
    )
    parser.add_argument(
        "--expected-repo",
        default=_DEFAULT_TRUSTED_REPO,
        help=f"The trusted repository (default: {_DEFAULT_TRUSTED_REPO}).",
    )
    parser.add_argument(
        "--expected-ref",
        default=_DEFAULT_TRUSTED_REF,
        help=f"The trusted ref (default: {_DEFAULT_TRUSTED_REF}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    trusted, _ = is_trusted(
        args.event_name,
        args.repository,
        args.expected_repo,
        args.ref,
        args.expected_ref,
        args.head_repository,
    )
    # stdout: the machine-readable decision the workflow branches on.
    print("true" if trusted else "false")
    # stderr: static audit trail only. CodeQL treats repository input as sensitive.
    print(
        "smoke trusted-context gate: trusted"
        if trusted
        else "smoke trusted-context gate: untrusted",
        file=sys.stderr,
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
