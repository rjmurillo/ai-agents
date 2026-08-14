#!/usr/bin/env python3
"""Shared infrastructure for the pre-PR validation check modules.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223) so the pre-PR
runner stays under the file-size limit and the area-specific check modules
(``checks_tooling``, ``checks_dash``, ``checks_spec``, ``checks_plugin``,
``checks_coverage``) share one home for the SKIP control-flow signal and the
git base-ref resolution helpers.

The subprocess wrapper itself lives in ``subprocess_runner`` (issue #4955, so
the timeout path can preserve partial child output without pushing this module
past the file-size ceiling) and is re-exported here as ``_run_subprocess``.

This began as a behavior-preserving move from ``pre_pr.py``. Later fixes can
land in these extracted modules directly while ``pre_pr`` re-exports them so
``from scripts.validation.pre_pr import MissingScriptSkip`` and the rest keep
working for existing callers and tests.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

if TYPE_CHECKING:
    # Type checkers resolve the sibling via its package path so the wrapper's
    # ``tuple[int, str, str]`` return type is preserved. Runtime uses the bare
    # import because ``pre_pr`` and ``checks_ratchet`` load this module as a
    # top-level name after inserting ``_SCRIPT_DIR`` on ``sys.path``.
    from scripts.validation.subprocess_runner import _run_subprocess
else:
    from subprocess_runner import _run_subprocess



class MissingScriptSkip(Exception):  # noqa: N818 - control-flow signal, not an error condition
    """Raised by a validation when a referenced script is absent on disk.

    Per ADR-042 (Python migration), several legacy PowerShell validators were
    expunged. Their absence should not produce a misleading [FAIL]; instead the
    validation is reported as SKIP and does not affect the overall exit code.
    """


def _git_subprocess_env() -> dict[str, str]:
    """Return a deterministic environment for nested git subprocess calls."""
    clean_env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        clean_env.pop(name, None)
    clean_env["LC_ALL"] = "C"
    return clean_env


def _upstream_head_ref_name(repo_root: Path) -> str | None:
    """Return the remote branch name the current branch is configured to track.

    Reads ``branch.<current>.merge``, which holds the full remote ref
    (``refs/heads/fix/gc-report-time-budget``) regardless of what the local
    branch is called. An isolated worktree checked out as ``pr-4294`` tracking
    a differently named PR head is the case this exists for (issue #4382).

    Returns None on a detached HEAD, an unconfigured upstream, or a value that
    is not a branch ref.
    """
    clean_env = _git_subprocess_env()
    branch_rc, branch_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
        env=clean_env,
        timeout=10,
    )
    branch = branch_out.strip()
    if branch_rc != 0 or not branch or branch == "HEAD":
        return None
    merge_rc, merge_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "config", "--get", f"branch.{branch}.merge"],
        env=clean_env,
        timeout=10,
    )
    if merge_rc != 0:
        return None
    ref = merge_out.strip()
    prefix = "refs/heads/"
    if not ref.startswith(prefix):
        return None
    return ref[len(prefix) :] or None


_NO_PR_MARKER = "no pull requests found"


class _PrViewProbe(NamedTuple):
    """One ``gh pr view`` attempt's outcome.

    ``no_pr_confirmed`` is True only when stderr contains the marker gh
    2.97.0 prints for a genuine "no PR" (verified against the installed
    binary): ``no pull requests found for branch "<name>"``, exit 1. Auth
    and network failures also exit 1 with different stderr, so exit code
    alone cannot distinguish them. Any other non-zero exit leaves this
    False (transient); the caller must not cache it.
    """

    base_ref: str | None
    no_pr_confirmed: bool
    exit_code: int
    stderr: str


def _gh_pr_base_ref_name(repo_root: Path, selector: list[str]) -> _PrViewProbe:
    """Probe ``gh pr view`` once for ``baseRefName``; never raises.

    ``selector``: ``[]`` infers the PR from the checked-out branch,
    ``[branch]`` names the head branch explicitly (issue #4382 retry).
    """
    exit_code, stdout, stderr = _run_subprocess(
        ["gh", "pr", "view", *selector, "--json", "baseRefName", "-q", ".baseRefName"],
        timeout=5,
        cwd=repo_root,
    )
    if exit_code == 0:
        return _PrViewProbe(stdout.strip() or None, False, exit_code, stderr)
    return _PrViewProbe(None, _NO_PR_MARKER in stderr.lower(), exit_code, stderr)


def _gh_base_ref_probe(repo_root: Path) -> tuple[str | None, bool, int, str]:
    """Uncached core of the PR-base query: bare lookup, then retry with the
    upstream head branch (issue #4382) -- but ONLY when the bare lookup
    explicitly confirmed no PR AND the upstream is not self-tracking. A
    transient failure (auth, network, rate limit) must not retry: it could
    look like a false confirmed "no PR" (round 2 review, item 4).
    Self-tracking (``git push -u origin HEAD``) would repeat the same
    confirmed query, so :func:`_is_self_tracking_upstream` (issue #2571)
    gates that too.

    Returns ``(base_ref, cacheable, exit_code, stderr)``; ``cacheable`` is
    True for a found PR or confirmed no-PR, False when transient -- see
    :func:`_gh_base_ref`, which must not cache the None it returns then.
    """
    probe = _gh_pr_base_ref_name(repo_root, [])
    if probe.base_ref:
        return f"origin/{probe.base_ref}", True, probe.exit_code, probe.stderr
    if not probe.no_pr_confirmed:
        return None, False, probe.exit_code, probe.stderr

    head = _upstream_head_ref_name(repo_root)
    if not head or _is_self_tracking_upstream(repo_root):
        return None, probe.no_pr_confirmed, probe.exit_code, probe.stderr

    probe2 = _gh_pr_base_ref_name(repo_root, [head])
    if probe2.base_ref:
        print(
            f"[base-ref] selected origin/{probe2.base_ref}: PR resolved by upstream head "
            f"'{head}' after the local branch name matched no PR",
            file=sys.stderr,
        )
        return f"origin/{probe2.base_ref}", True, probe2.exit_code, probe2.stderr
    return None, probe2.no_pr_confirmed, probe2.exit_code, probe2.stderr


def _branch_head_cache_key(repo_root: Path) -> tuple[str, str, str] | None:
    """Return ``(repo_root, branch, HEAD sha)`` for the cache key, or None
    when unavailable (detached HEAD, no git repo, no commits).
    """
    clean_env = _git_subprocess_env()
    branch_rc, branch_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
        env=clean_env,
        timeout=10,
    )
    branch = branch_out.strip()
    if branch_rc != 0 or not branch or branch == "HEAD":
        return None
    head_rc, head_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        env=clean_env,
        timeout=10,
    )
    head_sha = head_out.strip()
    if head_rc != 0 or not head_sha:
        return None
    return str(repo_root), branch, head_sha


# Cache for the gh PR-base query only; keyed on (repo_root, branch, HEAD sha).
_gh_pr_base_cache: dict[tuple[str, str, str], str | None] = {}
# Keys already warned about a transient failure, so repeats don't re-log.
_gh_pr_base_logged_failures: set[tuple[str, str, str]] = set()


def _reset_gh_base_cache() -> None:
    """Clear the gh PR-base cache and its logged-failure set (item 3).

    The cache key, ``(repo_root, branch, HEAD sha)``, is a proxy for "did
    the checkout change", not "did the remote PR change": two in-process
    invocations of ``pre_pr.py`` with an unchanged branch/HEAD would
    otherwise reuse a prior invocation's answer. ``pre_pr.main()`` calls
    this once at the top, scoping the cache to one invocation while still
    sharing it across every gate within that run.
    """
    _gh_pr_base_cache.clear()
    _gh_pr_base_logged_failures.clear()


def _gh_base_ref(repo_root: Path) -> str | None:
    """Return ``origin/<baseRefName>`` for the open PR, or None.

    Asks gh for the PR's base branch, then prefixes ``origin/`` so callers
    can pass the result to ``git diff`` directly. :func:`_gh_base_ref_probe`
    is the expensive part (``gh pr view``, ~0.42-0.49s/call); this wrapper
    caches ITS result keyed on ``(repo_root, branch, HEAD sha)`` so both
    resolver functions share one query per branch/HEAD state. A transient
    failure is NOT cached (retrying is correct once the condition clears);
    only success or a confirmed "no open PR" is cached, and the first
    non-authoritative failure per key is logged once, not once per gate.
    Retries with the upstream head branch per :func:`_gh_base_ref_probe`
    (issue #4382).

    A same-named, but NOT behaviorally identical, helper lives in
    ``.claude/hooks/PreToolUse/push_guard_base.py``; it lacks this retry.
    """
    if not shutil.which("gh"):
        return None

    key = _branch_head_cache_key(repo_root)
    if key is not None and key in _gh_pr_base_cache:
        return _gh_pr_base_cache[key]

    base_ref, cacheable, exit_code, stderr = _gh_base_ref_probe(repo_root)

    if key is None:
        return base_ref

    if cacheable:
        _gh_pr_base_cache[key] = base_ref
    elif key not in _gh_pr_base_logged_failures:
        _gh_pr_base_logged_failures.add(key)
        print(
            f"[WARN] base-ref: gh pr view did not give an authoritative answer "
            f"(exit {exit_code}): {stderr.strip() or '<no output>'}; not caching, "
            f"will retry on the next call",
            file=sys.stderr,
        )
    return base_ref


def _is_self_tracking_upstream(repo_root: Path) -> bool:
    """Return True when the branch's configured upstream tracks itself.

    After ``git push -u origin HEAD``, the branch's upstream is
    ``<remote>/<current_branch>`` -- it tracks itself, emptying a diff
    against it once pushed and silently no-opping "since base" gates
    (Issue #2571). Compares ``branch.<branch>.merge``
    (:func:`_upstream_head_ref_name`) to the branch name rather than
    string-comparing abbreviated ``@{u}`` against a hardcoded
    ``origin/<branch>``, which missed a non-``origin`` fork remote and
    branch names containing ``/``. ``@{u}`` resolvability is checked
    first, so a branch with no upstream returns False.
    """
    clean_env = _git_subprocess_env()
    branch_rc, branch_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
        env=clean_env,
        timeout=10,
    )
    if branch_rc != 0:
        return False
    branch = branch_out.strip()
    if not branch or branch == "HEAD":
        # Detached HEAD has no upstream; nothing to disambiguate.
        return False

    upstream_rc, upstream_out, _ = _run_subprocess(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ],
        env=clean_env,
        timeout=10,
    )
    if upstream_rc != 0:
        return False
    upstream = upstream_out.strip()
    if not upstream or "@{" in upstream:
        return False

    return _upstream_head_ref_name(repo_root) == branch


def _resolve_branch_base_ref(repo_root: Path) -> str | None:
    """Resolve the branch base ref by trying signals in priority order.

    Not cached itself (a bare ``functools.cache`` on the whole resolution
    had no invalidation hook); the expensive step, the network round trip
    inside :func:`_gh_base_ref` (``gh pr view``, ~0.42-0.49s/call), caches
    its own result keyed on ``(repo_root, branch, HEAD sha)``. The rest
    here is local, sub-millisecond git plumbing.

    Priority: (1) the PR's actual baseRefName via ``gh pr view``, validated
    with ``git rev-parse --verify`` so an unfetched ref falls through; (2)
    the current branch's ``@{u}``, EXCEPT when self-tracking (``origin/
    <branch>`` after ``git push -u origin HEAD``, which would empty-diff
    against HEAD and hide real changes, Issue #2571); (3) the remote
    default branch via ``refs/remotes/origin/HEAD``; (4) ``origin/main``.
    Returns None when none resolve.

    A related helper (``_detect_default_base_ref``) in
    ``.claude/hooks/PreToolUse/push_guard_base.py`` follows the same
    priority order and has its own separate test suite.
    """
    pr_base = _gh_base_ref(repo_root)
    if pr_base:
        exit_code, _, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", pr_base],
            timeout=10,
        )
        if exit_code == 0:
            print(f"[base-ref] selected {pr_base}: open PR base branch", file=sys.stderr)
            return pr_base

    # ``@{u}`` is the right base for derivative branches that track a parent
    # feature branch, so it stays in the candidate list. The self-tracking
    # case (the bug in Issue #2571) is filtered out here so the loop falls
    # through to ``refs/remotes/origin/HEAD``.
    skip_at_upstream = _is_self_tracking_upstream(repo_root)
    candidates = ("@{u}", "refs/remotes/origin/HEAD", "origin/main")
    for ref in candidates:
        if ref == "@{u}" and skip_at_upstream:
            continue
        exit_code, _, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", ref],
            timeout=10,
        )
        if exit_code == 0:
            print(
                f"[base-ref] selected {ref}: no PR base resolved, first "
                "candidate ref that exists locally",
                file=sys.stderr,
            )
            return ref
    return None


def _resolve_default_base_ref(repo_root: Path) -> str | None:
    """Resolve the base ref for "what changed vs the default branch".

    Unlike :func:`_resolve_branch_base_ref`, this deliberately EXCLUDES the
    current branch's own upstream (``@{u}``): for a feature branch ``@{u}``
    is ``origin/<feature-branch>``, and once pushed, ``@{u}...HEAD`` is
    empty, so a change-vs-base diff misses everything the branch added
    (issue #2571; ``pre_pr.py`` reported "No changed workflow files" while
    the pre-push hook, diffing against the merge-base with ``origin/main``,
    found one).

    Priority: (1) the PR's baseRefName via ``gh pr view`` (validated;
    shares :func:`_gh_base_ref`'s cache with :func:`_resolve_branch_base_ref`);
    (2) the remote default branch via ``refs/remotes/origin/HEAD``; (3)
    ``origin/main`` then local ``main`` as last-resort literals. Returns
    None when none resolve.
    """
    candidates: list[str] = []
    pr_base = _gh_base_ref(repo_root)
    if pr_base:
        candidates.append(pr_base)
    candidates += ["refs/remotes/origin/HEAD", "origin/main", "main"]
    for ref in candidates:
        exit_code, _, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", ref],
            timeout=10,
        )
        if exit_code == 0:
            return ref
    return None


def _refresh_remote_base(base_ref: str, repo_root: Path) -> str | None:
    """Best-effort fetch of ``origin/<branch>`` to keep the base ref fresh (#2453).

    A stale local ``origin/<branch>`` lets a validator false-PASS a bump
    that is insufficient against the real remote; refreshing here keeps the
    validator itself pure and offline-safe.

    Returns: None when no fetch was attempted (non-``origin/<branch>`` ref,
    or under CI where the runner already fetched); a short error string on
    a failed attempt (caller warns and proceeds); empty string on success.
    """
    if not base_ref.startswith("origin/"):
        return None
    if os.environ.get("CI", "").lower() in ("true", "1") or os.environ.get(
        "GITHUB_ACTIONS", ""
    ).lower() in ("true", "1"):
        return None
    branch = base_ref[len("origin/") :]
    if not branch or "/" in branch:
        # Refuse pathological inputs ("origin/", "origin/foo/bar/..."); a
        # straight branch name is the only safe target for a refresh.
        return None
    clean_env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        clean_env.pop(var, None)
    clean_env["LC_ALL"] = "C"

    exit_code, _, stderr = _run_subprocess(
        [
            "git",
            "-C",
            str(repo_root),
            "fetch",
            "--no-tags",
            "--quiet",
            "origin",
            branch,
        ],
        env=clean_env,
        timeout=15,
    )
    if exit_code == 0:
        return ""
    return stderr.strip() or f"git fetch exit {exit_code}"


def _run_build_script_gate(
    repo_root: Path,
    script_name: str,
    gate_label: str,
) -> bool:
    """Run a build script gate with standard error handling.

    Shared helper for gates that wrap a ``build/scripts/`` Python validator
    with the same pattern: check existence, resolve base ref, invoke with
    ``--base``, print output, and return success/failure.

    Args:
        repo_root: Repository root path.
        script_name: Filename under ``build/scripts/`` (e.g.
            ``validate_install_parity.py``).
        gate_label: Human-readable name for error messages (e.g.
            ``install-parity``).

    Returns: True if the script exits 0. Fails closed (False) when the
        script is absent or the base ref cannot be resolved.
    """
    script = repo_root / "build" / "scripts" / script_name
    if not script.exists():
        print(
            f"[ERROR] {script_name} absent; the {gate_label} gate cannot "
            f"run. Hard failure: the gate is the point of registering "
            f"this validator.",
            file=sys.stderr,
        )
        return False
    base_ref = _resolve_branch_base_ref(repo_root)
    if not base_ref:
        print(
            f"[ERROR] {gate_label} gate: base ref could not be resolved; "
            f"refusing to invoke validator without an explicit --base.",
            file=sys.stderr,
        )
        return False

    # Issue #2453: refresh origin/<branch> bases before validating so a stale
    # local ref does not false-PASS a bump that is actually insufficient
    # against the real remote. Best-effort; failure does not block.
    fetch_result = _refresh_remote_base(base_ref, repo_root)
    if fetch_result is not None and fetch_result != "":
        print(
            f"[WARN] {gate_label}: could not refresh {base_ref} "
            f"({fetch_result}); continuing with the local ref.",
            file=sys.stderr,
        )

    cmd = [sys.executable, str(script), "--base", base_ref]
    exit_code, stdout, stderr = _run_subprocess(cmd)
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:80]:
            print(line)
    return exit_code == 0
