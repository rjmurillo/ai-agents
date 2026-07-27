#!/usr/bin/env python3
"""Safe ``git push`` with explicit refspec and remote verification.

Issue #3412: the PR-maintenance autofix step pushed with a bare branch name
(``git push origin $HEAD_REF``) and never verified that the remote ref landed at
the requested commit. This helper pushes one explicit destination ref, verifies
that porcelain names only that ref, then confirms the remote with ``ls-remote``.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

EXIT_OK = 0
EXIT_VERIFICATION = 1
EXIT_USAGE = 2
EXIT_TRANSPORT = 3

_OK_FLAGS = frozenset({" ", "+", "*", "="})
_REJECT_FLAGS = frozenset({"!"})

class SafePushError(Exception):
    """Raised when the push cannot be issued or cannot be verified."""

    def __init__(self, message: str, exit_code: int, audit: PushAudit | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.audit = audit


@dataclass(frozen=True, slots=True)
class PorcelainRef:
    """One parsed ``git push --porcelain`` per-ref line."""

    flag: str
    source: str
    destination: str
    summary: str
    old_sha: str | None
    new_sha: str | None


@dataclass
class PushAudit:
    """Structured audit record for a single push attempt."""

    branch: str
    remote: str
    requested_refspec: str
    local_sha: str
    process_id: int
    verified: bool = False
    transport_flag: str | None = None
    remote_old_sha: str | None = None
    remote_new_sha: str | None = None
    observed_remote_sha: str | None = None
    expected_remote_sha: str | None = None
    returncode: int | None = None
    stderr: str = ""
    transport_text: str = ""
    error: str | None = None
    parsed_refs: list[dict[str, str | None]] = field(default_factory=list)


def _run_git(args: list[str], repo_root: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in ``repo_root`` capturing text output."""

    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git_stdout(args: list[str], repo_root: str, message: str) -> str:
    result = _run_git(args, repo_root)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SafePushError(f"{message}: {detail}", EXIT_TRANSPORT)
    return result.stdout.strip()


def _validate_branch_name(branch: str, repo_root: str) -> None:
    if not branch or branch.startswith("-") or branch == "HEAD":
        raise SafePushError(
            "--branch must be a non-empty branch name, not HEAD or a flag",
            EXIT_USAGE,
        )
    result = _run_git(["check-ref-format", "--branch", branch], repo_root)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SafePushError(f"invalid branch name {branch!r}: {detail}", EXIT_USAGE)


def _current_branch(repo_root: str) -> str:
    result = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], repo_root)
    if result.returncode != 0:
        raise SafePushError("refusing to push: HEAD is detached", EXIT_USAGE)
    return result.stdout.strip()


def _head_sha(repo_root: str) -> str:
    return _git_stdout(["rev-parse", "--verify", "HEAD"], repo_root, "cannot resolve HEAD sha")


def _assert_on_branch(branch: str, repo_root: str) -> None:
    _validate_branch_name(branch, repo_root)
    current = _current_branch(repo_root)
    if current != branch:
        raise SafePushError(
            "refusing to push: HEAD is on "
            f"{current!r} but requested branch is {branch!r}",
            EXIT_VERIFICATION,
        )


def _extract_new_sha(summary: str) -> tuple[str | None, str | None]:
    """Return ``(old_sha, new_sha)`` parsed from a porcelain summary."""

    token = summary.strip().split(" ", 1)[0]
    if "..." in token:
        old, new = token.split("...", 1)
        return old or None, new or None
    if ".." in token:
        old, new = token.split("..", 1)
        return old or None, new or None
    return None, None


def _parse_porcelain(stdout: str) -> list[PorcelainRef]:
    """Parse canonical porcelain lines from ``git push --porcelain`` stdout."""

    refs: list[PorcelainRef] = []
    for line in stdout.splitlines():
        if not line or line.startswith("To ") or line == "Done":
            continue
        fields = line.split("	")
        if len(fields) != 3 or len(fields[0]) != 1 or ":" not in fields[1]:
            continue
        source, destination = fields[1].split(":", 1)
        old_sha, new_sha = _extract_new_sha(fields[2])
        refs.append(
            PorcelainRef(
                flag=fields[0],
                source=source,
                destination=destination,
                summary=fields[2],
                old_sha=old_sha,
                new_sha=new_sha,
            )
        )
    return refs


def _porcelain_refs_for_audit(refs: list[PorcelainRef]) -> list[dict[str, str | None]]:
    return [asdict(ref) for ref in refs]


def _require_single_porcelain_ref(
    refs: list[PorcelainRef], dest_ref: str, audit: PushAudit
) -> PorcelainRef:
    audit.parsed_refs = _porcelain_refs_for_audit(refs)
    expected = [ref for ref in refs if ref.source == "HEAD" and ref.destination == dest_ref]
    if len(refs) != 1 or len(expected) != 1:
        audit.error = (
            "expected exactly one porcelain ref 'HEAD:"
            f"{dest_ref}', got {audit.parsed_refs or 'none'}"
        )
        raise SafePushError(audit.error, EXIT_VERIFICATION, audit)
    return expected[0]


def _ls_remote_sha(
    remote: str,
    dest_ref: str,
    repo_root: str,
    audit: PushAudit,
) -> str | None:
    result = _run_git(["ls-remote", "--refs", remote, dest_ref], repo_root)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        audit.error = f"git ls-remote failed for {dest_ref!r}: {detail}"
        raise SafePushError(audit.error, EXIT_TRANSPORT, audit)
    line = result.stdout.strip()
    if not line:
        return None
    fields = line.split("	")
    if len(fields) != 2 or fields[1] != dest_ref:
        audit.error = f"git ls-remote returned unexpected output for {dest_ref!r}: {line!r}"
        raise SafePushError(audit.error, EXIT_VERIFICATION, audit)
    return fields[0]


def _git_common_dir(repo_root: str) -> Path:
    value = _git_stdout(
        ["rev-parse", "--git-common-dir"],
        repo_root,
        "cannot resolve git common dir",
    )
    path = Path(value)
    if not path.is_absolute():
        path = Path(repo_root) / path
    return path.resolve()


@contextlib.contextmanager
def _branch_lock(repo_root: str, dest_ref: str) -> Iterator[None]:
    lock_dir = _git_common_dir(repo_root) / "safe-push-locks"
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    lock_name = hashlib.sha256(dest_ref.encode("utf-8")).hexdigest() + ".lock"
    with (lock_dir / lock_name).open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def safe_push(
    branch: str,
    remote: str,
    repo_root: str,
    expected_remote_sha: str | None = None,
    force_with_lease: bool = False,
) -> PushAudit:
    """Push ``HEAD`` to ``refs/heads/<branch>`` and verify the remote SHA."""

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
        expected_remote_sha=expected_remote_sha,
    )

    push_args = ["push", "--porcelain", remote, refspec]
    if force_with_lease:
        if not expected_remote_sha:
            audit.error = "--force-with-lease requires --expected-remote-sha"
            raise SafePushError(audit.error, EXIT_USAGE, audit)
        push_args.insert(2, f"--force-with-lease={dest_ref}:{expected_remote_sha}")

    with _branch_lock(repo_root, dest_ref):
        result = _run_git(push_args, repo_root)
        audit.returncode = result.returncode
        audit.stderr = result.stderr
        audit.transport_text = result.stdout + result.stderr
        refs = _parse_porcelain(result.stdout)
        audit.parsed_refs = _porcelain_refs_for_audit(refs)

        if result.returncode != 0:
            audit.error = f"git push exited {result.returncode}: {result.stderr.strip()}"
            raise SafePushError(audit.error, EXIT_TRANSPORT, audit)

        pushed_ref = _require_single_porcelain_ref(refs, dest_ref, audit)
        audit.transport_flag = pushed_ref.flag
        audit.remote_old_sha = pushed_ref.old_sha
        audit.remote_new_sha = pushed_ref.new_sha

        if pushed_ref.flag in _REJECT_FLAGS:
            audit.error = f"remote rejected {dest_ref!r}: {pushed_ref.summary.strip()}"
            raise SafePushError(audit.error, EXIT_TRANSPORT, audit)
        if pushed_ref.flag not in _OK_FLAGS:
            audit.error = f"unexpected transport flag {pushed_ref.flag!r} for {dest_ref!r}"
            raise SafePushError(audit.error, EXIT_TRANSPORT, audit)

        observed_sha = _ls_remote_sha(remote, dest_ref, repo_root, audit)
        audit.observed_remote_sha = observed_sha
        audit.remote_new_sha = observed_sha or audit.remote_new_sha
        if observed_sha != local_sha:
            audit.error = (
                f"remote {dest_ref!r} is {observed_sha or 'missing'}, "
                f"expected local sha {local_sha}"
            )
            raise SafePushError(audit.error, EXIT_VERIFICATION, audit)

    audit.verified = True
    return audit


def _emit_audit(audit: PushAudit) -> None:
    print(json.dumps(asdict(audit), sort_keys=True), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Push HEAD to a named branch with explicit refspec and remote "
            "verification (issue #3412)."
        )
    )
    parser.add_argument(
        "--branch",
        required=True,
        help="Expected branch name and push destination.",
    )
    parser.add_argument("--remote", default="origin", help="Remote name.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository working directory to run git in.",
    )
    parser.add_argument(
        "--expected-remote-sha",
        help="Remote SHA required by --force-with-lease=<dest>:<sha>.",
    )
    parser.add_argument(
        "--force-with-lease",
        action="store_true",
        help="Use --force-with-lease for intentional non-fast-forward updates.",
    )
    args = parser.parse_args(argv)

    try:
        audit = safe_push(
            args.branch,
            args.remote,
            args.repo_root,
            expected_remote_sha=args.expected_remote_sha,
            force_with_lease=args.force_with_lease,
        )
    except SafePushError as exc:
        if exc.audit is not None:
            failed = exc.audit
            failed.error = str(exc)
        else:
            try:
                local_sha = _head_sha(args.repo_root)
            except SafePushError:
                local_sha = ""
            failed = PushAudit(
                branch=args.branch,
                remote=args.remote,
                requested_refspec=f"HEAD:refs/heads/{args.branch}",
                local_sha=local_sha,
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
