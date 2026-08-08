"""Shared CI runner infrastructure for validation scripts.

Provides common utilities for CI entry points that need to fetch base refs,
resolve diff bases, and run subprocesses. Used by:
- run_install_parity_ci.py
- run_plugin_version_bump_ci.py

Both validators need a diff base, and the resolution logic is identical.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Allowlist for env-supplied refs (defense in depth; subprocess uses argv, no
# shell). Branch: letters, digits, slash, hyphen, underscore, dot. SHA: 7-40 hex.
_BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]{1,200}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def validate_branch(name: str) -> str | None:
    """Return ``name`` when it matches the branch allowlist, else None."""
    name = name.strip()
    if not name or not _BRANCH_RE.match(name):
        return None
    if ".." in name or name.startswith("-"):
        return None
    return name


def validate_sha(value: str) -> str | None:
    """Return ``value`` when it matches the SHA allowlist, else None."""
    value = value.strip()
    if not value or not _SHA_RE.match(value):
        return None
    if value == "0" * len(value):
        return None
    return value


def run(
    cmd: list[str], *, check: bool = False, timeout: int = 60
) -> tuple[int, str, str]:
    """Run a subprocess by argv. Returns (exit_code, stdout, stderr).

    Not vulnerable to CWE-78 (command injection): ``cmd`` is an argv list and
    ``subprocess.run`` is called without ``shell=True``, so no string is ever
    handed to a shell for re-parsing. Env-supplied refs (``PR_BASE_REF``,
    ``PUSH_BEFORE_SHA``) reach this function only after passing the
    ``validate_branch`` / ``validate_sha`` allowlists, which reject anything
    outside ``[A-Za-z0-9_./-]`` and forbid a leading ``-`` so a ref cannot be
    smuggled in as a git option. The values are git refs, never raw user input.
    """
    try:
        proc = subprocess.run(  # nosemgrep: dangerous-subprocess-use-tainted-env-args
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def fetch_base_ref(base_ref: str) -> int:
    """Fetch the base ref without leaving a shallow graft behind.

    The previous form ran `--depth=200` unconditionally and then `--unshallow`,
    with both tolerating failure. On the two callers' workflows the checkout is
    already `fetch-depth: 0`, so the depth-limited fetch bought nothing and its
    only effect was to write `.git/shallow`. The `--unshallow` that followed
    normally repaired that, which is why nothing had ever been observed to
    break, but its failure was swallowed: a timeout on a 165 MiB fetch left the
    graft in place and the comment's "next step (rev-parse) is the
    authoritative check" does not catch it, because `rev-parse` resolves a base
    ref perfectly well on a grafted clone. Every range measured afterwards is
    then wrong rather than absent (issue #4680).

    So: do not graft a complete clone at all, and when the clone really is
    shallow, verify the repair took instead of assuming it.

    An unrepaired graft is reported as a return value, not an exception. It is
    an expected environment condition rather than a programming error, both
    callers already return 2 for their other config failures, and a raise here
    would leave `main()` with no handler, so Python would exit 1 with a
    traceback instead of the 2 the exit-code contract calls for.

    The probe is three-valued. Only a confirmed `True` justifies `--unshallow`,
    because a complete clone rejects that option. A failed probe cannot prove
    complete history, so it returns the configuration error before fetching.

    Returns:
        0  the base ref is fetched and the clone has complete history
        2  the fetch failed or the clone is still shallow
    """
    shallow = _is_shallow_repository()
    if shallow is None:
        print(
            "error: could not determine whether the repository is shallow; "
            "refusing to measure a potentially incomplete range.",
            file=sys.stderr,
        )
        return 2
    if shallow is False:
        code, stdout, stderr = run(
            ["git", "fetch", "--no-tags", "origin", base_ref],
            check=False,
            timeout=120,
        )
        if code != 0:
            _print_fetch_error(base_ref, stdout, stderr)
            return 2
        return 0

    # `--unshallow` fetches the ref AND completes the history, so the old
    # `--depth=200` fetch that preceded it was a second network round trip and
    # a second timeout window that preserved no invariant.
    code, stdout, stderr = run(
        ["git", "fetch", "--no-tags", "--unshallow", "origin", base_ref],
        check=False,
        timeout=180,
    )
    if code != 0:
        _print_fetch_error(base_ref, stdout, stderr)
        return 2
    if _is_shallow_repository() is not False:
        print(
            "error: repository is still shallow after --unshallow, so any "
            "range measured from here would silently widen rather than fail. "
            "Run `git fetch --unshallow origin` and retry.",
            file=sys.stderr,
        )
        return 2
    return 0


def _print_fetch_error(base_ref: str, stdout: str, stderr: str) -> None:
    """Report a failed fetch using the runner's configuration contract."""
    print(f"error: git fetch failed for origin/{base_ref}", file=sys.stderr)
    if stdout:
        sys.stderr.write(stdout)
    if stderr:
        sys.stderr.write(stderr)


def _is_shallow_repository() -> bool | None:
    """True, False, or None when git could not answer."""
    code, stdout, _ = run(
        ["git", "rev-parse", "--is-shallow-repository"], check=False, timeout=30
    )
    if code != 0:
        return None
    value = stdout.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def resolve_base(base_ref: str) -> str | None:
    """Return the diff base, or None when no usable ref resolves.

    Order:
      1. ``origin/<base_ref>`` when it resolves AND differs from ``HEAD``.
         This is the correct base for pull_request events and for incremental
         pushes on feature branches: the gate enforces "strictly greater than
         the version at the base ref", so the base is the base branch
         (typically ``main``), not the previous tip of the feature branch.
      2. ``PUSH_BEFORE_SHA`` when set and resolvable. Reserved for the case
         where ``origin/<base_ref>`` equals ``HEAD`` (direct push to the base
         branch yields an empty origin diff) or ``origin/<base_ref>`` cannot
         be resolved (fetch failure, deleted base ref). Covers every commit
         in the push, not just the last one.
      3. ``HEAD^`` as a last resort. Single-commit fallback only.

    Regression note (#2254): Before the fix, ``PUSH_BEFORE_SHA`` was checked
    first unconditionally, which false-failed feature-branch incremental
    pushes whose previous tip already contained the version bump.
    """
    rc_origin, origin_sha, _ = run(
        ["git", "rev-parse", "--verify", "--quiet", f"origin/{base_ref}"], timeout=10
    )
    origin_resolves = rc_origin == 0
    if origin_resolves:
        rc_head, head_sha, _ = run(
            ["git", "rev-parse", "--verify", "--quiet", "HEAD"], timeout=10
        )
        # Prefer origin/<base_ref> unless it equals HEAD (a direct push to the
        # base branch, where the origin diff would be empty).
        if rc_head != 0 or head_sha.strip() != origin_sha.strip():
            return f"origin/{base_ref}"

    push_before = validate_sha(os.environ.get("PUSH_BEFORE_SHA", ""))
    if push_before is not None:
        rc, _, _ = run(
            ["git", "rev-parse", "--verify", "--quiet", push_before], timeout=10
        )
        if rc == 0:
            return push_before

    if origin_resolves:
        # origin/<base_ref> resolved but equalled HEAD and PUSH_BEFORE_SHA was
        # unusable; fall back to it anyway so callers get a defined base.
        return f"origin/{base_ref}"

    rc, _, _ = run(["git", "rev-parse", "--verify", "--quiet", "HEAD^"], timeout=10)
    if rc == 0:
        return "HEAD^"
    return None
