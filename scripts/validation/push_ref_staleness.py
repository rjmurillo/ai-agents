#!/usr/bin/env python3
"""Pre-push staleness check: detect when the remote ref advanced during the hook run.

The Lefthook pre-push suite can run for 6-15 minutes. During that window,
another process (typically rjmurillo-bot merging main into the branch) may
push to the same remote ref. When git finally tries to push, it gets:

  ! [remote rejected] branch -> branch
    (cannot lock ref: is at <new-sha> but expected <old-sha>)

That rejection is confusing and wastes the full hook run. This script runs
as an early check in the pre-push group, reads STDIN to discover which
refs are being pushed, compares the current local HEAD against the remote
ref RIGHT NOW (before the long hooks run), and exits 3 (external) if the
remote has already advanced beyond the local commit's parent chain.

Exit codes follow ADR-035 (.agents/architecture/ADR-035-exit-code-standardization.md,
table at line 41: "2 | Usage/configuration error | Missing required param, invalid
argument, not in git repo"):
    0 - Remote ref matches expectation; safe to proceed
    1 - Logic error (missing git)
    2 - Configuration error: the hook argument is an unexpanded placeholder,
        so no remote can be identified and no check is possible
    3 - External: remote has advanced; push will be rejected; abort early
    4 - Auth error

Usage (lefthook pre-push job; lefthook expands "{1}" to the pushed remote):
    uv run --frozen python scripts/validation/push_ref_staleness.py "{1}"

Or for testing (the remote argument is optional and defaults to origin):
    echo "refs/heads/mybranch <local-sha> refs/heads/mybranch <remote-sha>" \\
      | python scripts/validation/push_ref_staleness.py
"""

from __future__ import annotations

import re
import subprocess
import sys

_DEFAULT_REMOTE = "origin"

# Lefthook substitutes a positional placeholder only when the hook received that
# argument, and it never substitutes a name it does not know, so `{1}` (manual
# `lefthook run pre-push` with no arguments) or `{remote}` (issue #4634) can
# reach this script as literal text. Probed against lefthook 2.1.10, the version
# pinned by `min_version` in lefthook.yml:
#     run: printf 'ARG1=[{1}] ARG2=[{2}] ALL=[{0}]\n'
#     lefthook run pre-push          -> ARG1=[{1}] ARG2=[{2}] ALL=[]
#     lefthook run pre-push origin U -> ARG1=[origin] ARG2=[U] ALL=[origin U]
_UNEXPANDED_PLACEHOLDER = re.compile(r"^\{[^{}]*\}$")


def _resolve_remote(argv: list[str] | None) -> str | None:
    """Return the remote to query, or None when the argument names no remote.

    `lefthook.yml` passes the pre-push hook's first positional argument as
    `"{1}"`, which git sets to the remote name or URL being pushed to. Two
    inputs must never reach `git ls-remote` as a remote name:

    - Nothing at all. Direct invocation for testing (see the module docstring)
      has no hook arguments, and `origin` is the right default there.
    - An unexpanded placeholder such as `{1}` or `{remote}`. This means the job
      definition is wrong, so the caller gets exit 2 and no check runs.

    Both used to produce a name no remote can resolve, which `_remote_sha`
    reports as None and `main` reads as "new branch, no race is possible", so
    every push passed a check that examined nothing. That silent pass is issue
    #4634. Substituting `origin` for a placeholder would reintroduce the same
    class of defect from the other side: on a push to some other remote the
    check would compare against an unrelated ref and exit 0, reporting a clean
    result for a comparison nobody asked for. A misconfigured job fails loudly
    instead.
    """
    candidate = argv[0].strip() if argv else ""
    if not candidate:
        return _DEFAULT_REMOTE
    if _UNEXPANDED_PLACEHOLDER.match(candidate):
        print(
            f"[push-ref-staleness] Hook argument {candidate!r} is an unexpanded "
            "placeholder, not a remote name. The lefthook job must pass the "
            'pre-push remote as "{1}"; see issue #4634.',
            file=sys.stderr,
        )
        return None
    return candidate


def _run(cmd: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _remote_sha(remote: str, refspec: str) -> str | None:
    """Return the SHA the remote currently has for refspec, or None if absent."""
    result = _run(["git", "ls-remote", remote, refspec])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    # Output: "<sha>\t<refspec>"
    parts = result.stdout.strip().split()
    return parts[0] if parts else None


def _is_ancestor(older: str, newer: str) -> bool:
    """Return True when older is an ancestor of newer in the local graph."""
    result = _run(["git", "merge-base", "--is-ancestor", older, newer])
    return result.returncode == 0


def _stale_refs(lines: list[str], remote: str) -> list[str]:
    """Return one human-readable line per pushed ref the remote has moved past.

    Each stdin line is `<local-ref> <local-sha> <remote-ref> <remote-sha>`,
    where the last field is what git believed the remote held at its last
    fetch. A ref is stale when the live remote SHA differs from that belief and
    the local commit does not already contain it.
    """
    stale: list[str] = []

    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue

        _local_ref, local_sha, remote_ref, cached_remote_sha = parts[:4]

        # Deletion push: remote_sha is zeros, skip.
        if local_sha == "0" * 40:
            continue

        # Query the remote right now.
        live_sha = _remote_sha(remote, remote_ref)

        if live_sha is None:
            # New branch being pushed for the first time; no race possible.
            continue

        if live_sha == cached_remote_sha:
            # Remote hasn't moved since our last fetch; no race.
            continue

        # Remote has a SHA we haven't fetched. Check whether our local commit
        # already contains the remote's new commit (i.e. we fetched and merged).
        if _is_ancestor(live_sha, local_sha):
            # Our branch is ahead of or equal to the remote; safe to push.
            continue

        # Remote advanced past us. The push will be rejected.
        stale.append(
            f"  {remote_ref}: remote is at {live_sha[:12]}, "
            f"expected {cached_remote_sha[:12]}"
        )

    return stale


def main(argv: list[str] | None = None) -> int:
    """Check each pushed ref against its current remote state.

    Reads push data from stdin in the format git sends to pre-push hooks:
        <local-ref> <local-sha> <remote-ref> <remote-sha>

    The remote-sha in the stdin line is what git THINKS is on the remote
    (from the last fetch). We re-query the live remote to detect races.
    """
    lines = sys.stdin.read().splitlines()
    if not lines:
        # Nothing to push or called without stdin; pass through.
        return 0

    # Drain stdin before validating the argument so the caller's write side
    # always has a reader, and so an empty push list costs nothing.
    remote = _resolve_remote(argv)
    if remote is None:
        # ADR-035: 2 = usage/configuration error. Exiting nonzero here is the
        # point; a job that cannot name its remote must not report success.
        return 2

    stale_refs = _stale_refs(lines, remote)

    if stale_refs:
        print(
            "[push-ref-staleness] Remote ref(s) advanced during this hook run.",
            file=sys.stderr,
        )
        print(
            "Fetch and merge before pushing (or rebase). Aborting to save hook time:",
            file=sys.stderr,
        )
        for msg in stale_refs:
            print(msg, file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
