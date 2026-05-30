#!/usr/bin/env python3
"""Install the canonical git hooks for this repository.

The repository ships its enforced hooks under ``.githooks/`` (pre-commit,
pre-push). Git only runs them when ``core.hooksPath`` points at that directory.
A fresh clone defaults to ``.git/hooks`` instead, so the pre-push guards
(workflow validation, plugin version-bump gate, Python tests) never run locally
and bad pushes slip through to CI.

This script sets ``core.hooksPath`` to ``.githooks`` (idempotent), verifies the
hook scripts exist and are executable, and warns about a legacy
``.git/hooks/pre-push`` shim that would otherwise be shadowed.

Canonical mechanism documented in ``docs/technical-guardrails.md`` and
``scripts/bootstrap-vm.sh`` (``git config core.hooksPath .githooks``).

Modes:

* default: configure ``core.hooksPath`` and verify hooks.
* ``--check``: verify only, never mutate. Exit non-zero if not configured or
  hooks are missing. Useful for a setup assertion.

Exit codes (per AGENTS.md): 0 ok, 1 logic (hooks missing/not executable or
``--check`` found misconfiguration), 2 config (not a git repo / no .githooks),
3 external (a git command failed).
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

HOOKS_DIR_NAME = ".githooks"
# Hook files that must be present and executable for enforcement to work.
REQUIRED_HOOKS = ("pre-commit", "pre-push")

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command, capturing output. Raises on a missing git binary.

    Uses ``-C`` and strips ``GIT_DIR``/``GIT_WORK_TREE`` from the environment
    so that git always operates on the specified ``cwd``, ignoring any
    repository override variables the caller may have inherited.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def find_repo_root(start: Path) -> Path | None:
    """Return the git work-tree root containing ``start``, or None."""
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=start)
    if result.returncode != 0:
        return None
    top = result.stdout.strip()
    return Path(top) if top else None


def get_git_common_dir(repo_root: Path) -> Path | None:
    """Return the shared git directory (common dir) for this repository.

    For a regular checkout, this is the same as ``.git``. For a linked worktree,
    this returns the main repository's ``.git`` directory, which is where shared
    config (including ``core.hooksPath``) should be written so all worktrees
    inherit the setting.
    """
    result = _run_git(["rev-parse", "--git-common-dir"], cwd=repo_root)
    if result.returncode != 0:
        return None
    common = result.stdout.strip()
    if not common:
        return None
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = repo_root / common_path
    return common_path.resolve()


def get_hooks_path(repo_root: Path) -> str | None:
    """Return the configured ``core.hooksPath`` value, or None if unset."""
    result = _run_git(["config", "--get", "core.hooksPath"], cwd=repo_root)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def hooks_path_points_at_canonical(repo_root: Path, value: str | None) -> bool:
    """True if ``value`` is a relative path resolving to ``.githooks``.

    Absolute paths are rejected even if they resolve to ``.githooks``, because
    they break worktrees: secondary worktrees do not get per-tree hook
    resolution when an absolute path is written to the shared ``.git/config``.
    """
    if not value:
        return False
    candidate = Path(value)
    if candidate.is_absolute():
        return False
    canonical = (repo_root / HOOKS_DIR_NAME).resolve()
    candidate = repo_root / candidate
    try:
        return candidate.resolve() == canonical
    except OSError:
        return False


def set_hooks_path(repo_root: Path) -> bool:
    """Point ``core.hooksPath`` at ``.githooks`` in the shared repository config.

    Uses ``--file`` targeting the shared config so linked worktrees inherit the
    setting. Without this, ``git config`` from a linked worktree writes to the
    worktree's private config, leaving other worktrees (including the primary
    checkout) with an unset ``core.hooksPath``.
    """
    common_dir = get_git_common_dir(repo_root)
    if common_dir is None:
        return False
    shared_config = common_dir / "config"
    result = _run_git(
        ["config", "--file", str(shared_config), "core.hooksPath", HOOKS_DIR_NAME],
        cwd=repo_root,
    )
    return result.returncode == 0


def verify_hooks(repo_root: Path) -> list[str]:
    """Return a list of problems with the ``.githooks`` directory.

    Empty list means every required hook exists and is executable.
    """
    problems: list[str] = []
    hooks_dir = repo_root / HOOKS_DIR_NAME
    if not hooks_dir.is_dir():
        problems.append(f"missing hooks directory: {hooks_dir}")
        return problems
    for name in REQUIRED_HOOKS:
        hook = hooks_dir / name
        if not hook.is_file():
            problems.append(f"missing hook: {hook}")
            continue
        mode = hook.stat().st_mode
        if not mode & stat.S_IXUSR:
            problems.append(f"hook not executable: {hook}")
    return problems


def detect_legacy_shim(repo_root: Path) -> Path | None:
    """Return the path to a legacy ``.git/hooks/pre-push`` shim if present.

    Once ``core.hooksPath`` points at ``.githooks`` this file is shadowed and
    never runs, so a stale copy is a foot-gun worth flagging.
    """
    legacy = repo_root / ".git" / "hooks" / "pre-push"
    return legacy if legacy.is_file() else None


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify configuration without modifying anything.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success output (errors still print to stderr).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Override repo root detection (mainly for tests).",
    )
    return parser


def _print_problems(problems: list[str]) -> None:
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)


def _run_check(
    repo_root: Path, *, configured: bool, current: str | None, quiet: bool
) -> int:
    if not configured:
        print(
            "error: core.hooksPath is not set to "
            f"{HOOKS_DIR_NAME} (current: {current or 'unset'}); "
            "run scripts/install_git_hooks.py",
            file=sys.stderr,
        )
        return EXIT_LOGIC
    problems = verify_hooks(repo_root)
    if problems:
        _print_problems(problems)
        return EXIT_LOGIC
    _print(
        f"OK: core.hooksPath -> {HOOKS_DIR_NAME}, hooks present", quiet=quiet
    )
    return EXIT_OK


def _run_install(
    repo_root: Path, *, configured: bool, current: str | None, quiet: bool
) -> int:
    if configured:
        _print(
            f"core.hooksPath already set to {HOOKS_DIR_NAME}", quiet=quiet
        )
    elif not set_hooks_path(repo_root):
        print("error: failed to set core.hooksPath", file=sys.stderr)
        return EXIT_EXTERNAL
    else:
        _print(
            f"set core.hooksPath -> {HOOKS_DIR_NAME} (was: {current or 'unset'})",
            quiet=quiet,
        )
        # Re-read effective path to detect higher-precedence overrides (e.g. worktree-local config)
        effective = get_hooks_path(repo_root)
        if not hooks_path_points_at_canonical(repo_root, effective):
            print(
                f"error: core.hooksPath was written to shared config but effective "
                f"value is '{effective or 'unset'}'; "
                "a higher-precedence config (e.g. worktree-local) is overriding it. "
                "Run: git config --unset core.hooksPath",
                file=sys.stderr,
            )
            return EXIT_LOGIC

    problems = verify_hooks(repo_root)
    if problems:
        _print_problems(problems)
        return EXIT_LOGIC

    legacy = detect_legacy_shim(repo_root)
    if legacy is not None:
        _print(
            f"warning: legacy hook {legacy} is now shadowed by "
            f"{HOOKS_DIR_NAME}/pre-push and will not run; "
            "delete it to avoid confusion",
            quiet=quiet,
        )

    _print("git hooks installed", quiet=quiet)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    start = Path(args.repo_root) if args.repo_root else Path.cwd()
    repo_root = find_repo_root(start)
    if repo_root is None:
        print(f"error: not a git repository: {start}", file=sys.stderr)
        return EXIT_CONFIG

    if not (repo_root / HOOKS_DIR_NAME).is_dir():
        print(
            f"error: {HOOKS_DIR_NAME}/ not found under {repo_root}; "
            "this does not look like the ai-agents repo",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    current = get_hooks_path(repo_root)
    configured = hooks_path_points_at_canonical(repo_root, current)

    if args.check:
        return _run_check(
            repo_root, configured=configured, current=current, quiet=args.quiet
        )
    return _run_install(
        repo_root, configured=configured, current=current, quiet=args.quiet
    )


if __name__ == "__main__":
    raise SystemExit(main())
