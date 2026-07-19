#!/usr/bin/env python3
"""Activate the repository's ``.githooks`` on session start (Issue #3182).

SessionStart hook that guarantees ``core.hooksPath`` points at ``.githooks``
for every local agent session, so ``.githooks/pre-commit`` and
``.githooks/pre-push`` run on every commit and push. Without deterministic
activation, a fresh clone leaves ``core.hooksPath`` unset and the only
enforcement is the late ``pre_pr.py`` gate, after commits and pushes have
already bypassed the hook layer. Guaranteeing activation here is the
prerequisite for retiring the PreToolUse commit/push guards (Epic #3197).

The activation itself is delegated to the tested, idempotent installer
``scripts/install_git_hooks.py`` (worktree-safe shared-config write,
absolute-path rejection). This hook only decides WHEN to run it and always
exits 0.

Behavior (Issue #3182 requirements):
    REQ-2: no ``.githooks/`` at the project root (a plugin consumer repo) ->
        exit 0 without touching git config.
    REQ-3: ``core.hooksPath`` already resolves to ``.githooks`` -> the
        installer is a no-op and prints nothing under ``--quiet``.
    REQ-4: any activation failure (git missing, write error, installer absent)
        -> one-line warning naming ``python3 scripts/install_git_hooks.py``
        and exit 0. SessionStart hooks cannot block; ``pre_pr.py`` stays the
        blocking backstop.

Hook Type: SessionStart (non-blocking, fail-open)
Exit Codes:
    0 = Always (fail-open; never wedge session start)

References:
    - Issue #3182 (deterministic .githooks activation)
    - scripts/install_git_hooks.py (idempotent installer this delegates to)
    - .agents/SESSION-PROTOCOL.md
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HOOK_NAME = "git-hooks-activation"
HOOKS_DIR_NAME = ".githooks"
INSTALLER_RELPATH = Path("scripts") / "install_git_hooks.py"
MANUAL_FIX = "python3 scripts/install_git_hooks.py"
# Bound the installer so a wedged git call never hangs session start.
INSTALLER_TIMEOUT_SECONDS = 10


def project_directory() -> str:
    """Resolve the session's project root (CLAUDE_PROJECT_DIR, else cwd)."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return str(Path(env_dir).resolve())
    return str(Path.cwd())


def _drain_stdin() -> None:
    """Consume stdin so the harness pipe never blocks (fail-open)."""
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except OSError:
            pass


def _warn(message: str) -> None:
    print(f"[WARNING] {HOOK_NAME}: {message}", file=sys.stderr)


def activate(project_dir: str) -> None:
    """Ensure core.hooksPath is set for ``project_dir`` via the installer."""
    root = Path(project_dir)
    # REQ-2: repositories that do not ship the hook layer (plugin consumers)
    # get a no-op. Never write git config in a repo without .githooks.
    if not (root / HOOKS_DIR_NAME).is_dir():
        return

    installer = root / INSTALLER_RELPATH
    if not installer.is_file():
        _warn(f"installer not found at {INSTALLER_RELPATH}; run: {MANUAL_FIX}")
        return

    # Delegate to the idempotent installer. --quiet keeps an already-configured
    # clone silent (REQ-3); a fresh clone is activated exactly once.
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(installer),
                "--quiet",
                "--repo-root",
                str(root),
            ],
            capture_output=True,
            text=True,
            timeout=INSTALLER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _warn(f"could not run the git-hooks installer ({exc}); run: {MANUAL_FIX}")
        return

    # REQ-4: any non-zero exit is surfaced as one warning line and swallowed;
    # pre_pr.py remains the blocking backstop.
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        reason = detail[-1] if detail else f"installer exited {result.returncode}"
        _warn(f"{reason}; run: {MANUAL_FIX}")


def main() -> None:
    _drain_stdin()
    activate(project_directory())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail-open: never block session start
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
    sys.exit(0)
