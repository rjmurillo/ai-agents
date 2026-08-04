#!/usr/bin/env python3
"""Safe ``git push`` with explicit refspec and remote verification.

Issue #3412: the PR-maintenance autofix step pushed with a bare branch name
(``git push origin $HEAD_REF``) and never verified that the remote ref landed at
the requested commit. This helper pushes the resolved object id, verifies
that porcelain names only that object and destination, then confirms the remote
with ``ls-remote``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import NoReturn, cast

EXIT_OK = 0
EXIT_VERIFICATION = 1
EXIT_USAGE = 2
EXIT_TRANSPORT = 3

_OK_FLAGS = frozenset({" ", "+", "*", "="})
_REJECT_FLAGS = frozenset({"!"})

# Kept in sync by name with FORCE_PUSH_ESCAPE_ENV in
# scripts/validation/git_hook_policy.py, which reads it as
# `os.environ.get(FORCE_PUSH_ESCAPE_ENV) == "1"`.
FORCE_PUSH_ESCAPE_ENV = "FORCE_PUSH_OK"


def _load_object_id_validator(
    module_path: Path | None = None,
) -> Callable[[str], bool]:
    if module_path is None:
        module_path = (
            Path(__file__).resolve().parents[2]
            / "scripts"
            / "validation"
            / "object_id.py"
        )
    spec = importlib.util.spec_from_file_location("safe_push_object_id", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load object id validator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError) as exc:
        raise RuntimeError(
            f"cannot load object id validator from {module_path}: {exc}"
        ) from exc
    try:
        validator = vars(module)["is_full_object_id"]
    except KeyError as exc:
        raise RuntimeError(
            f"object id validator {module_path} does not define is_full_object_id"
        ) from exc
    if not callable(validator):
        raise RuntimeError(
            f"object id validator {module_path} defines a non-callable "
            "is_full_object_id"
        )
    return cast(Callable[[str], bool], validator)


is_full_object_id = _load_object_id_validator()


class SafePushArgumentParser(argparse.ArgumentParser):
    """Argument parser that raises SafePushError with EXIT_USAGE on parser errors."""

    def error(self, message: str) -> NoReturn:
        raise SafePushError(message, EXIT_USAGE)


def _expected_remote_sha_arg(value: str) -> str:
    if not is_full_object_id(value):
        raise argparse.ArgumentTypeError(
            "--expected-remote-sha must be a full 40 or 64 character hexadecimal object id"
        )
    return value


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


def _run_git(
    args: list[str], repo_root: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a git command in ``repo_root`` capturing text output."""

    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )


def _force_push_env() -> dict[str, str]:
    """Return the child environment that lets the pre-push guard pass a lease.

    `_check_non_fast_forward` in `scripts/validation/git_hook_policy.py` blocks
    any update whose remote tip is not reachable from the local tip. It cannot
    see argv, so a `--force-with-lease` pinned to an observed remote SHA looks
    identical to a blind `--force` and gets rejected with exit 1. The lease is
    the stronger check of the two: it refuses at the remote if the tip moved
    off the SHA we observed, which is exactly the loss the guard exists to
    prevent. `FORCE_PUSH_OK=1` is the escape `.claude/rules/universal.md`
    MUST NOT 1 sanctions for that case; every other pre-push job still runs.
    """

    env = os.environ.copy()
    env[FORCE_PUSH_ESCAPE_ENV] = "1"
    return env


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
    refs: list[PorcelainRef], source_ref: str, dest_ref: str, audit: PushAudit
) -> PorcelainRef:
    audit.parsed_refs = _porcelain_refs_for_audit(refs)
    expected = [
        ref
        for ref in refs
        if ref.source == source_ref and ref.destination == dest_ref
    ]
    if len(refs) != 1 or len(expected) != 1:
        audit.error = (
            "expected exactly one porcelain ref "
            f"{source_ref!r}:{dest_ref!r}, got {audit.parsed_refs or 'none'}"
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



def safe_push(
    branch: str,
    remote: str,
    repo_root: str,
    expected_remote_sha: str | None = None,
    force_with_lease: bool = False,
) -> PushAudit:
    """Push the resolved HEAD commit to ``refs/heads/<branch>`` and verify it."""

    _assert_on_branch(branch, repo_root)
    local_sha = _head_sha(repo_root)
    dest_ref = f"refs/heads/{branch}"
    refspec = f"{local_sha}:{dest_ref}"
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
        if expected_remote_sha is None:
            audit.error = "--force-with-lease requires --expected-remote-sha"
            raise SafePushError(audit.error, EXIT_USAGE, audit)
        if not is_full_object_id(expected_remote_sha):
            audit.error = (
                "--expected-remote-sha must be a full 40 or 64 character "
                "hexadecimal object id"
            )
            raise SafePushError(audit.error, EXIT_USAGE, audit)
        push_args.insert(2, f"--force-with-lease={dest_ref}:{expected_remote_sha}")

    push_env = _force_push_env() if force_with_lease else None
    result = _run_git(push_args, repo_root, push_env)
    audit.returncode = result.returncode
    audit.stderr = result.stderr
    audit.transport_text = result.stdout + result.stderr
    refs = _parse_porcelain(result.stdout)
    audit.parsed_refs = _porcelain_refs_for_audit(refs)

    if result.returncode != 0:
        audit.error = f"git push exited {result.returncode}: {result.stderr.strip()}"
        raise SafePushError(audit.error, EXIT_TRANSPORT, audit)

    pushed_ref = _require_single_porcelain_ref(refs, local_sha, dest_ref, audit)
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
    parser = SafePushArgumentParser(
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
        type=_expected_remote_sha_arg,
        help="Remote SHA required by --force-with-lease=<dest>:<sha>.",
    )
    parser.add_argument(
        "--force-with-lease",
        action="store_true",
        help="Use --force-with-lease for intentional non-fast-forward updates.",
    )
    try:
        args = parser.parse_args(argv)
    except SafePushError as exc:
        print(f"::error::safe push failed: {exc}", file=sys.stderr)
        return exc.exit_code

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
