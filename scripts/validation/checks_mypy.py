"""Mypy changed-files gate for the pre-PR runner (Issue #4674).

Extracted from checks_tooling.py to keep that module under the 500-line ceiling.
Reuses git_hook_policy.run_mypy which implements ratchet semantics: tolerates
pre-existing errors and fails only when the change adds new ones.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _resolve_branch_base_ref, _run_subprocess  # noqa: E402


def validate_mypy_changed_files(repo_root: Path) -> bool:
    """Run mypy over Python files changed on the branch (ratchet semantics).

    Surfaces type regressions at pre-PR time rather than waiting for push CI.
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print("[WARNING] Mypy gate skipped: no base ref resolved")
        return True

    exit_code, stdout, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "diff", "--name-only",
         "--diff-filter=ACMR", f"{base_ref}...HEAD"],
        timeout=30,
    )
    if exit_code != 0:
        print("[WARNING] Mypy gate skipped: git diff failed")
        return True

    py_files = [
        p for p in stdout.splitlines()
        if p.endswith(".py") and (repo_root / p).is_file()
    ]
    if not py_files:
        print("[PASS] Mypy (no Python files changed on branch)")
        return True

    print(f"Type-checking {len(py_files)} changed Python file(s)...")
    from git_hook_policy import run_mypy

    return bool(run_mypy(py_files, repo_root) == 0)
