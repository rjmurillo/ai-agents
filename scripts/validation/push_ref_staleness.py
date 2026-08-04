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

Exit codes follow ADR-035:
    0 - Remote ref matches expectation; safe to proceed
    1 - Logic error (bad arguments, missing git)
    2 - Not found (ref or remote does not exist - non-fatal, proceed)
    3 - External: remote has advanced; push will be rejected; abort early
    4 - Auth error

Usage (called by lefthook pre-push hook):
    git push ... | python scripts/validation/push_ref_staleness.py

Or for testing:
    echo "refs/heads/mybranch <local-sha> refs/heads/mybranch <remote-sha>" \\
      | python scripts/validation/push_ref_staleness.py
"""

from __future__ import annotations

import subprocess
import sys


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

    remote = argv[0] if argv else "origin"

    stale_refs: list[str] = []

    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue

        local_ref, local_sha, remote_ref, _cached_remote_sha = parts[:4]

        # Deletion push: remote_sha is zeros, skip.
        if local_sha == "0" * 40:
            continue

        # Query the remote right now.
        live_sha = _remote_sha(remote, remote_ref)

        if live_sha is None:
            # New branch being pushed for the first time; no race possible.
            continue

        if live_sha == _cached_remote_sha:
            # Remote hasn't moved since our last fetch; no race.
            continue

        # Remote has a SHA we haven't fetched. Check whether our local commit
        # already contains the remote's new commit (i.e. we fetched and merged).
        if _is_ancestor(live_sha, local_sha):
            # Our branch is ahead of or equal to the remote; safe to push.
            continue

        # Remote advanced past us. The push will be rejected.
        stale_refs.append(
            f"  {remote_ref}: remote is at {live_sha[:12]}, "
            f"expected {_cached_remote_sha[:12]}"
        )

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
