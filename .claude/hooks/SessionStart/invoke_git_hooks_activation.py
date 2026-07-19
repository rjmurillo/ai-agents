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
    REQ-2: no ``.githooks/`` at the project root -> exit 0 without touching git
        config. The hook also no-ops when it is not tracked inside the repo it
        would activate (a downstream consumer running the shipped plugin against
        an unrelated repo), so the repo-relative installer is never
        consumer-controlled. See ``_is_self_repository``.
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
    """Resolve the repository root for this session.

    Anchor on ``CLAUDE_PROJECT_DIR`` when the harness sets it, else the current
    directory, then walk up to the git top level so activation is deterministic
    even when the session starts in a subdirectory. A fresh clone leaves
    ``core.hooksPath`` unset regardless of cwd, so anchoring on a bare cwd would
    silently no-op the REQ-2 ``.githooks`` check from a nested directory.
    ``git rev-parse --show-toplevel`` is a Layer-1 built-in; on any failure fall
    back to the anchor unchanged (fail-open).
    """
    anchor = os.environ.get("CLAUDE_PROJECT_DIR", "").strip() or str(Path.cwd())
    anchor = str(Path(anchor).resolve())
    try:
        result = subprocess.run(
            ["git", "-C", anchor, "rev-parse", "--show-toplevel"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=INSTALLER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return anchor
    if result.returncode == 0:
        top = result.stdout.strip()
        if top:
            return str(Path(top).resolve())
    return anchor


def _drain_stdin() -> None:
    """Consume stdin so the harness pipe never blocks (fail-open)."""
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except OSError:
            pass


def _warn(message: str) -> None:
    print(f"[WARNING] {HOOK_NAME}: {message}", file=sys.stderr)


def _is_self_repository(root: Path) -> bool:
    """True when this hook file is tracked inside ``root``.

    The activation delegates to ``root/scripts/install_git_hooks.py``. Running a
    repo-relative script is only safe when this hook is part of the repository
    being activated (an ai-agents working copy). When the hook runs from an
    installed plugin whose directory sits outside ``root`` (a downstream
    consumer opening an unrelated repo), that installer path would be
    consumer-controlled, so a hostile repo shipping its own
    ``scripts/install_git_hooks.py`` could achieve code execution on session
    start. Refusing to run unless the hook lives inside ``root`` closes that
    vector while keeping the self/dogfooding case working (the tracked hook and
    installer share the same repo root). See PR #3244 / CodeRabbit review.
    """
    try:
        Path(__file__).resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def activate(project_dir: str) -> None:
    """Ensure core.hooksPath is set for ``project_dir`` via the installer."""
    root = Path(project_dir)
    # REQ-2: repositories that do not ship the hook layer get a no-op. Never
    # write git config in a repo without .githooks.
    if not (root / HOOKS_DIR_NAME).is_dir():
        return

    # Only run the repo-relative installer when this hook is tracked inside the
    # repository being activated. A consumer running the shipped plugin against
    # an unrelated (possibly hostile) repo takes this no-op path.
    if not _is_self_repository(root):
        return

    installer = root / INSTALLER_RELPATH
    if not installer.is_file():
        _warn(f"installer not found at {INSTALLER_RELPATH}; run: {MANUAL_FIX}")
        return

    # Delegate to the idempotent installer. --quiet keeps an already-configured
    # clone silent (REQ-3); a fresh clone is activated exactly once.
    try:
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args
        # Dear future maintainer: Semgrep taints this call because --repo-root
        # derives from CLAUDE_PROJECT_DIR / cwd (env-sourced). It is a false
        # positive and a scoped suppression is the only clean silence: the call
        # is list-form argv (no shell, so command injection is impossible), the
        # executable is the fixed Python interpreter, and ``installer`` is only
        # reached after ``_is_self_repository`` confirms this hook is tracked
        # inside ``root`` -- so the installer is always this repository's own
        # tracked scripts/install_git_hooks.py, never an attacker-controlled
        # path. Restructuring cannot remove the taint: the repo root must come
        # from the environment. See PR #3244.
        result = subprocess.run(
            [
                sys.executable,
                str(installer),
                "--quiet",
                "--repo-root",
                str(root),
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
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
