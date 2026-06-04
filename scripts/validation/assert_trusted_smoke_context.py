#!/usr/bin/env python3
"""Gate the authenticated CLI smoke to a trusted execution context (issue #2231 item 3).

The nightly smoke installs the real Copilot/Claude CLIs and runs a hook end to
end. That needs auth secrets, so the run MUST NOT execute attacker-controlled
code with those secrets in scope. Per ``.claude/rules/security.md`` and the
issue-3 requirement ("run from a trusted ref only, do not auto-run the probe on
fork PRs"), this script is the trusted-context gate. Per ADR-006 the decision
lives here, not in workflow YAML.

The smoke workflow triggers only on ``schedule`` and ``workflow_dispatch``,
which GitHub never fires from a fork. This gate is defense in depth: it
re-checks the event and the repository so that adding a new trigger later (or a
misconfigured fork of this repo) cannot silently start running the probe with
secrets. It fails closed: anything it cannot positively confirm is untrusted.

Authorized when ALL hold:
- ``--event-name`` is ``schedule`` or ``workflow_dispatch`` (never a PR, so a
  fork PR can never reach the secret-bearing job).
- ``--repository`` equals the expected trusted repo (default
  ``rjmurillo/ai-agents``), so a fork running this workflow on its own schedule
  does not match and is denied.
- ``--ref`` equals the expected trusted ref (default ``refs/heads/main``), so a
  manual dispatch from another branch cannot run code with smoke secrets.

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

_TRUSTED_EVENTS = frozenset({"schedule", "workflow_dispatch"})
_DEFAULT_TRUSTED_REPO = "rjmurillo/ai-agents"
_DEFAULT_TRUSTED_REF = "refs/heads/main"


def is_trusted(
    event_name: str,
    repository: str,
    expected_repo: str,
    ref: str = _DEFAULT_TRUSTED_REF,
    expected_ref: str = _DEFAULT_TRUSTED_REF,
) -> tuple[bool, str]:
    """Return ``(trusted, reason)`` for the given execution context.

    Fail-closed: an unrecognized event or a non-matching repository is untrusted.
    """
    if event_name not in _TRUSTED_EVENTS:
        allowed = ", ".join(sorted(_TRUSTED_EVENTS))
        return (False, f"event is not a trusted trigger (allowed: {allowed})")
    if repository.casefold() != expected_repo.casefold():
        return (False, "repository is not the trusted repo")
    if ref != expected_ref:
        return (False, "ref is not the trusted ref")
    return (True, "trusted context: approved event, repo, and ref")


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
