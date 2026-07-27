#!/usr/bin/env python3
"""Safe ``git push`` with explicit refspec and transport verification.

Issue #3412: the PR-maintenance autofix step pushed with a bare branch name
(``git push origin $HEAD_REF``) and never verified that the transport result
actually updated the requested ref. A push reported success while the requested
branch stayed unchanged, and the transport line named an unrelated branch. A
false success lets the operator believe a PR was updated when it was not, and
can coincide with mutating another branch.

This helper closes that gap:

- It refuses to push unless ``HEAD`` is on the expected branch, so a detached
  HEAD or a wrong-branch checkout cannot push the wrong content.
- It pushes with an explicit ``HEAD:refs/heads/<branch>`` refspec, so git cannot
  fall back to ``push.default`` matching behavior or DWIM a different ref.
- It parses ``git push --porcelain`` and fails unless the requested
  ``refs/heads/<branch>`` appears in the transport result and lands at the exact
  local SHA that was pushed.
- It emits a structured JSON audit record (requested refspec, local SHA, remote
  old and new SHA, process id, transport flag, and the full transport text) so a
  future misdirected push is observable rather than silent.

Exit codes (ADR aligned): 0 success, 1 logic or verification failure, 2 usage
or configuration error, 3 external git or transport failure.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field

EXIT_OK = 0
EXIT_VERIFICATION = 1
EXIT_USAGE = 2
EXIT_TRANSPORT = 3

# ``git push --porcelain`` per-ref flags. See ``git-push(1)`` PORCELAIN OUTPUT.
_OK_FLAGS = frozenset({" ", "+", "*", "="})
_REJECT_FLAGS = frozenset({"!"})


class SafePushError(Exception):
    """Raised when the push cannot be issued or cannot be verified.

    ``exit_code`` carries the process exit status the CLI should surface so a
    verification failure (1) is distinguishable from a transport failure (3).
    """

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class PushAudit:
    """Structured audit record for a single push attempt.

    Emitted as JSON so a misdirected or no-op push is observable after the fact,
    satisfying the issue #3412 requirement to record the requested refspec,
    local SHA, remote SHA, process id, and transport result of each push.
    """

    branch: str
    remote: str
    requested_refspec: str
    local_sha: str
    process_id: int
    verified: bool = False
    transport_flag: str | None = None
    remote_old_sha: str | None = None
    remote_new_sha: str | None = None
    returncode: int | None = None
    transport_text: str = ""
    error: str | None = None
    parsed_refs: list[str] = field(default_factory=list)


def _run_git(
    args: list[str], repo_root: str
) -> subprocess.CompletedProcess[str]:
    """Run a git command in ``repo_root`` capturing text output.

    ``encoding`` and ``errors`` are pinned so tool glyphs cannot crash the
    reader thread on Windows (cp1252 default), which would otherwise leave
    ``stdout`` as ``None``.
    """

    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _current_branch(repo_root: str) -> str:
    """Return the checked-out branch name, or ``"HEAD"`` when detached."""

    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if result.returncode != 0:
        raise SafePushError(
            f"cannot resolve current branch: {result.stderr.strip()}",
            EXIT_TRANSPORT,
        )
    return result.stdout.strip()


def _head_sha(repo_root: str) -> str:
    result = _run_git(["rev-parse", "HEAD"], repo_root)
    if result.returncode != 0:
        raise SafePushError(
            f"cannot resolve HEAD sha: {result.stderr.strip()}",
            EXIT_TRANSPORT,
        )
    return result.stdout.strip()


def _assert_on_branch(branch: str, repo_root: str) -> None:
    """Refuse the push unless HEAD is exactly on ``branch``.

    This blocks the wrong-branch and detached-HEAD leak scenarios: a push may
    only proceed when the checkout is on the branch the caller intends to
    update.
    """

    current = _current_branch(repo_root)
    if current != branch:
        raise SafePushError(
            "refusing to push: HEAD is on "
            f"{current!r} but requested branch is {branch!r}",
            EXIT_VERIFICATION,
        )


def _parse_porcelain(stdout: str) -> dict[str, tuple[str, str]]:
    """Map each destination ref to ``(flag, summary)`` from porcelain output.

    ``git push --porcelain`` prints ``To <url>`` then one tab-separated line per
    ref: ``<flag>\\t<from>:<to>\\t<summary>`` and a trailing ``Done``. The
    destination ref (``<to>``) is the key the caller verifies against.
    """

    refs: dict[str, tuple[str, str]] = {}
    for line in stdout.splitlines():
        if not line or line.startswith("To ") or line == "Done":
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        flag = fields[0]
        from_to = fields[1]
        summary = fields[2] if len(fields) > 2 else ""
        if ":" not in from_to:
            continue
        _, dest = from_to.split(":", 1)
        refs[dest] = (flag, summary)
    return refs


def _extract_new_sha(summary: str) -> tuple[str | None, str | None]:
    """Return ``(old_sha, new_sha)`` parsed from a porcelain summary.

    Updated refs report ``<old>..<new>``; new refs report ``[new branch]`` with
    no SHAs. Returns ``(None, None)`` when SHAs are not present.
    """

    token = summary.strip().split(" ", 1)[0]
    if ".." in token:
        old, _, new = token.partition("..")
        return old or None, new or None
    return None, None


def safe_push(branch: str, remote: str, repo_root: str) -> PushAudit:
    """Push ``HEAD`` to ``refs/heads/<branch>`` on ``remote`` and verify it.

    Returns a populated :class:`PushAudit` on success. Raises
    :class:`SafePushError` if the checkout is on the wrong branch, if git fails,
    or if the transport result does not confirm the requested ref reached the
    local SHA.
    """

    _assert_on_branch(branch, repo_root)
    local_sha = _head_sha(repo_root)
    dest_ref = f"refs/heads/{branch}"
    refspec = f"HEAD:{dest_ref}"
    audit = PushAudit(
        branch=branch,
        remote=remote,
        requested_refspec=refspec,
        local_sha=local_sha,
        process_id=os.getpid(),
    )

    result = _run_git(["push", "--porcelain", remote, refspec], repo_root)
    audit.returncode = result.returncode
    audit.transport_text = result.stdout + result.stderr
    refs = _parse_porcelain(result.stdout)
    audit.parsed_refs = sorted(refs)

    if dest_ref not in refs:
        audit.error = (
            f"requested refspec {refspec!r} is absent from the transport "
            f"result; refs seen: {audit.parsed_refs or 'none'}"
        )
        raise SafePushError(audit.error, EXIT_VERIFICATION)

    flag, summary = refs[dest_ref]
    audit.transport_flag = flag
    audit.remote_old_sha, audit.remote_new_sha = _extract_new_sha(summary)

    if flag in _REJECT_FLAGS:
        audit.error = f"remote rejected {dest_ref!r}: {summary.strip()}"
        raise SafePushError(audit.error, EXIT_TRANSPORT)

    if flag not in _OK_FLAGS:
        audit.error = f"unexpected transport flag {flag!r} for {dest_ref!r}"
        raise SafePushError(audit.error, EXIT_TRANSPORT)

    if result.returncode != 0:
        audit.error = (
            f"git push exited {result.returncode} despite naming {dest_ref!r}"
        )
        raise SafePushError(audit.error, EXIT_TRANSPORT)

    # Defense in depth: when the transport reports a new SHA it must be the
    # exact commit we pushed. A mismatch means the ref moved to content we did
    # not intend (the issue #3412 misdirection signature).
    if audit.remote_new_sha and not local_sha.startswith(audit.remote_new_sha):
        audit.error = (
            f"transport updated {dest_ref!r} to {audit.remote_new_sha}, "
            f"expected local sha {local_sha}"
        )
        raise SafePushError(audit.error, EXIT_VERIFICATION)

    audit.verified = True
    return audit


def _emit_audit(audit: PushAudit) -> None:
    """Write the audit record as one JSON line to stderr."""

    print(json.dumps(asdict(audit), sort_keys=True), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Push HEAD to a named branch with explicit refspec and transport "
            "verification (issue #3412)."
        )
    )
    parser.add_argument(
        "--branch",
        required=True,
        help="Expected branch name; HEAD must be on it and it is the push dest.",
    )
    parser.add_argument("--remote", default="origin", help="Remote name.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository working directory to run git in.",
    )
    args = parser.parse_args(argv)

    if not args.branch or args.branch.startswith("-"):
        print("::error::--branch must be a non-empty branch name", file=sys.stderr)
        return EXIT_USAGE

    try:
        audit = safe_push(args.branch, args.remote, args.repo_root)
    except SafePushError as exc:
        failed = PushAudit(
            branch=args.branch,
            remote=args.remote,
            requested_refspec=f"HEAD:refs/heads/{args.branch}",
            local_sha="",
            process_id=os.getpid(),
            error=str(exc),
        )
        _emit_audit(failed)
        print(f"::error::safe push failed: {exc}", file=sys.stderr)
        return exc.exit_code

    _emit_audit(audit)
    print(
        f"::notice::pushed {audit.branch} -> {audit.remote} "
        f"at {audit.local_sha} (verified)"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
