#!/usr/bin/env python3
"""Shared infrastructure for the pre-PR validation check modules.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223) so the pre-PR
runner stays under the file-size limit and the area-specific check modules
(``checks_tooling``, ``checks_dash``, ``checks_spec``, ``checks_plugin``,
``checks_coverage``) share one home for the subprocess wrapper, the
SKIP control-flow signal, and the git base-ref resolution helpers.

This began as a behavior-preserving move from ``pre_pr.py``. Later fixes can
land in these extracted modules directly while ``pre_pr`` re-exports them so
``from scripts.validation.pre_pr import MissingScriptSkip`` and the rest keep
working for existing callers and tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class MissingScriptSkip(Exception):  # noqa: N818 - control-flow signal, not an error condition
    """Raised by a validation when a referenced script is absent on disk.

    Per ADR-042 (Python migration), several legacy PowerShell validators were
    expunged. Their absence should not produce a misleading [FAIL]; instead the
    validation is reported as SKIP and does not affect the overall exit code.
    """


def _run_subprocess(
    args: list[str],
    timeout: int = 300,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess and return (exit_code, stdout, stderr).

    When ``env`` is provided it replaces the child environment entirely, so
    callers that only want to add a variable should merge it with
    ``os.environ`` themselves before passing it in.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"


def _git_subprocess_env() -> dict[str, str]:
    """Return a deterministic environment for nested git subprocess calls."""
    clean_env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        clean_env.pop(name, None)
    clean_env["LC_ALL"] = "C"
    return clean_env


def _gh_base_ref(repo_root: Path) -> str | None:
    """Return ``origin/<baseRefName>`` for the open PR, or None.

    Asks the gh CLI for the PR's base branch name, then prefixes
    ``origin/`` so callers can pass the result to ``git diff`` directly.

    Behavior:
    - If gh is not on PATH, return None.
    - If gh succeeds but no PR exists for the current branch (empty
      output), return None.
    - If gh exits non-zero (auth, network, unknown error), return None.

    A related helper (``_gh_base_ref``) lives in
    ``.claude/hooks/PreToolUse/push_guard_base.py`` for use inside the
    pre-push framework. Find it via
    ``grep -n '^def _gh_base_ref' .claude/hooks/PreToolUse/push_guard_base.py``.
    The two functions evolved separately and intentionally cover
    different runtime contexts (CI vs developer machine). Test coverage
    in this codebase locks in the public contract above; the canonical
    file does the same in its own test suite.
    """
    if not shutil.which("gh"):
        return None
    exit_code, stdout, _ = _run_subprocess(
        ["gh", "pr", "view", "--json", "baseRefName", "-q", ".baseRefName"],
        timeout=5,
        cwd=repo_root,
    )
    if exit_code != 0:
        return None
    base = stdout.strip()
    if not base:
        return None
    return f"origin/{base}"


def _is_self_tracking_upstream(repo_root: Path) -> bool:
    """Return True when ``@{u}`` resolves to the current branch's own remote ref.

    After ``git push -u origin HEAD`` (the default contributor workflow), the
    branch's configured upstream is ``origin/<current_branch>`` -- i.e. the
    branch tracks itself. Using that ref as a diff base produces an empty
    range once the branch is pushed and HEAD == origin/<branch>, which makes
    every "since base" gate silently no-op (Issue #2571).

    This helper is intentionally pure (queries git only, no side effects) so
    callers can decide whether to fall back to a trunk-pointing ref.
    Non-self upstreams (a derivative branch tracking a parent feature branch)
    return False; those should still be honoured.
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

    return upstream == f"origin/{branch}"


def _resolve_branch_base_ref(repo_root: Path) -> str | None:
    """Resolve the branch base ref by trying signals in priority order.

    Tries each candidate in order and returns the first one that
    resolves to a real ref locally:

        1. The PR's actual baseRefName via ``gh pr view`` (validated
           further with ``git rev-parse --verify`` so an unfetched ref
           falls through to the next step).
        2. The current branch's configured upstream via ``@{u}``, EXCEPT
           when the upstream is the branch's own ``origin/<branch>``
           (self-tracking after ``git push -u origin HEAD``). A
           self-tracking upstream produces an empty diff against HEAD
           once the branch is pushed, which would let "since base"
           gates miss real changes -- the bug behind Issue #2571.
        3. The remote's default branch via ``refs/remotes/origin/HEAD``.
        4. ``origin/main`` as a last-resort literal.

    Returns None when none resolve.

    A related helper (``_detect_default_base_ref``) lives in
    ``.claude/hooks/PreToolUse/push_guard_base.py`` and follows the same
    priority order; locate it via
    ``grep -n '^def _detect_default_base_ref' .claude/hooks/PreToolUse/push_guard_base.py``
    if you want the pre-push framework's perspective. The two functions
    have separate test suites that lock in their respective contracts.
    """
    pr_base = _gh_base_ref(repo_root)
    if pr_base:
        exit_code, _, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", pr_base],
            timeout=10,
        )
        if exit_code == 0:
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
            return ref
    return None


def _resolve_default_base_ref(repo_root: Path) -> str | None:
    """Resolve the base ref for "what changed vs the default branch".

    Unlike :func:`_resolve_branch_base_ref`, this deliberately EXCLUDES the
    current branch's own upstream (``@{u}``). For a feature branch ``@{u}`` is
    ``origin/<feature-branch>``; once the branch is pushed, ``@{u}...HEAD`` is
    empty, so a change-vs-base diff misses everything the branch added. That is
    exactly how ``pre_pr.py`` reported "No changed workflow files" while the
    pre-push hook (which diffs against the merge-base with ``origin/main``)
    found and validated one (issue #2571).

    Priority order:

        1. The PR's actual baseRefName via ``gh pr view`` (validated).
        2. The remote default branch via ``refs/remotes/origin/HEAD``.
        3. ``origin/main`` then local ``main`` as last-resort literals.

    Returns None when none resolve.
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

    The wrapper invokes a base-ref-using validator with the local
    ``origin/<branch>`` ref. When the local ref is stale (the developer has
    not fetched in a while), the validator compares against an old version
    and false-PASSes a bump that is actually insufficient against the real
    remote. Refreshing here, in the wrapper, keeps the validator itself pure
    and offline-safe.

    Returns:
        ``None`` when no fetch was attempted (non-``origin/<branch>`` ref, or
        running under CI where the CI runner already fetched). A short error
        string when the fetch was attempted and failed; the caller emits a
        WARNING and proceeds. Empty string on a successful fetch.
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
        script_name: Filename under ``build/scripts/`` (e.g.,
            ``validate_install_parity.py``).
        gate_label: Human-readable name for error messages (e.g.,
            ``install-parity``).

    Returns:
        True if the script exits 0, False otherwise. Fails closed when
        the script is absent or when the base ref cannot be resolved.
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
