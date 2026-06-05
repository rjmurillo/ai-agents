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
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"


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


def _resolve_branch_base_ref(repo_root: Path) -> str | None:
    """Resolve the branch base ref by trying signals in priority order.

    Tries each candidate in order and returns the first one that
    resolves to a real ref locally:

        1. The PR's actual baseRefName via ``gh pr view`` (validated
           further with ``git rev-parse --verify`` so an unfetched ref
           falls through to the next step).
        2. The current branch's configured upstream via ``@{u}``.
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

    candidates = ("@{u}", "refs/remotes/origin/HEAD", "origin/main")
    for ref in candidates:
        exit_code, _, _ = _run_subprocess(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", ref],
            timeout=10,
        )
        if exit_code == 0:
            return ref
    return None


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
    cmd = [sys.executable, str(script), "--base", base_ref]
    exit_code, stdout, stderr = _run_subprocess(cmd)
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:80]:
            print(line)
    return exit_code == 0
