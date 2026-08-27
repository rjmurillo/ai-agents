#!/usr/bin/env python3
"""Install git hook shims that no single worktree can poison.

Git keeps one hooks directory per repository, in ``$GIT_COMMON_DIR/hooks``, and
every linked worktree reads that same directory. ``check_git_hook_health.py``
records the measurement verbatim in its module docstring:

    ``git rev-parse --git-path hooks`` returns the directory git will actually
    read: it honors ``core.hooksPath`` (absolute or relative), and in a linked
    worktree it resolves to the common directory's ``hooks/`` rather than
    ``.git/worktrees/<name>/hooks``

``lefthook install`` writes its shim into that shared directory, and the shim
lefthook 2.1.10 generates embeds an absolute path probed from whichever
environment ran the install. Measured in this repository on 2026-08-27, the
shared ``pre-commit`` held::

    elif /home/user/ai-agents/.claude/worktrees/wf_54440bac-347-6/.venv/[...]

where the elided tail is ``lib/python3.14/site-packages/lefthook/bin/`` plus
the platform binary, and the reader was worktree ``wf_54440bac-347-8``. Running
``lefthook install --reset-hooks-path`` from ``-8`` rewrote that same shared
line to ``-8``'s own ``.venv``. Worktrees are deleted routinely, so the shared
hook ends up naming an interpreter that no longer exists, for every other
checkout of the repository. ``.config/wt.toml`` ran that install on every new
worktree, so the churn was continuous (issue #4789).

This installer writes a shim that names no worktree-specific path at all. It
resolves lefthook through ``uv run --frozen`` at hook-run time, from the cwd
git sets, which is the top level of the worktree the hook fired in. One shared
file, correct for every checkout.

Stricter/looser/different than canonical
----------------------------------------
Different from ``lefthook install``: this writes a fixed template instead of
lefthook's environment-probed one, so it drops lefthook's fallback chain
(``node_modules``, ``swift``, ``mint``, ``mise``, ``devbox``, a bare ``lefthook``
on PATH). Those fallbacks are what carried the poisoned absolute path. This
repository resolves lefthook through ``uv`` (``lefthook.yml`` line 3 reads
``lefthook: uv run --frozen lefthook``), so the dropped rungs were unreachable
here anyway: lefthook templates that value into a constant-true ``test -n``
guard, so its first branch always won.

It still runs ``lefthook install --reset-hooks-path`` first, so lefthook clears
any ``core.hooksPath`` override and records its own
``$GIT_COMMON_DIR/info/lefthook.checksum`` state, then overwrites the shim files
lefthook just wrote. ``--check`` never runs the install and never mutates.

Known limitation, not closed here
---------------------------------
``lefthook run`` re-syncs the hooks itself whenever the config checksum has
gone stale. Measured on lefthook 2.1.10: editing ``lefthook.yml`` after an
install and then running ``lefthook run pre-commit`` renamed the existing hook
to ``pre-commit.old`` and wrote a fresh environment-probed shim in its place.
So a ``lefthook.yml`` edit re-poisons the shared hook. The pre-PR gate
``Lefthook Installed`` detects that state and names this script as the repair;
closing it entirely would need lefthook to stop auto-syncing, which this change
does not attempt.

USAGE:
  # Install worktree-safe shims (mutates $GIT_COMMON_DIR/hooks):
  uv run python scripts/maintenance/install_lefthook_worktree_safe.py

  # Report only; exit non-zero when a shim diverges, mutate nothing:
  uv run python scripts/maintenance/install_lefthook_worktree_safe.py --check

EXIT CODES (ADR-035):
  0 - Shims are worktree-safe (or were just made so)
  1 - --check found a divergent, missing, or non-executable shim
  2 - Configuration error: not a git worktree, or no lefthook config present
  3 - External error: `lefthook install` failed or git could not be queried

Refs Issue #4789.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_GIT_TIMEOUT_SECONDS = 30
_INSTALL_TIMEOUT_SECONDS = 300

# Kept byte-identical with check_git_hook_health.py's LEFTHOOK_CONFIG_NAMES so
# both agree on what "this repository uses lefthook" means.
LEFTHOOK_CONFIG_NAMES = tuple(
    f"{stem}{local}.{extension}"
    for stem in ("lefthook", ".lefthook", ".config/lefthook")
    for local in ("", "-local")
    for extension in ("yml", "yaml", "json", "jsonc", "toml")
)

# Client-side git hooks. Used as an allowlist over the config's top-level keys
# so non-hook settings (`lefthook:`, `colors:`, `templates:`) are never mistaken
# for a hook name. Server-side hooks are excluded: git never runs them here.
GIT_CLIENT_HOOKS = frozenset(
    {
        "applypatch-msg",
        "commit-msg",
        "post-applypatch",
        "post-checkout",
        "post-commit",
        "post-merge",
        "post-rewrite",
        "pre-applypatch",
        "pre-auto-gc",
        "pre-commit",
        "pre-merge-commit",
        "pre-push",
        "pre-rebase",
        "prepare-commit-msg",
        "push-to-checkout",
        "sendemail-validate",
    }
)

# A top-level YAML mapping key: no leading whitespace, no leading list dash.
_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):")

_HOOK_MODE = 0o755

# The signature of the defect this installer exists to prevent: an absolute
# path reaching into some checkout's virtual environment.
_VENV_PATH = re.compile(r"(?:^|[\s\"'])/\S*/\.venv/")

REPAIR_COMMAND = "uv run python scripts/maintenance/install_lefthook_worktree_safe.py"


class GitQueryError(RuntimeError):
    """Git was unavailable or refused to answer."""


def hook_shim(hook: str) -> str:
    """Return the shim body for ``hook``.

    Every line is environment-independent. ``uv`` and ``LEFTHOOK_BIN`` are
    resolved from PATH and the environment at hook-run time, never baked in, so
    the one shared copy of this file is correct in every worktree.

    ``LEFTHOOK=0``, ``LEFTHOOK_BIN``, and ``LEFTHOOK_VERBOSE`` keep the meanings
    lefthook's own shim gives them. Preserving them is deliberate: ADR-086 and
    ``.claude/rules/universal.md`` MUST NOT 2 name ``LEFTHOOK=0`` and
    ``LEFTHOOK_BIN`` as forbidden bypasses, and a rule against using a
    mechanism is not a reason to silently remove it from under the people the
    rule binds.
    """
    return f"""#!/bin/sh
# Worktree-safe lefthook shim for the "{hook}" hook.
#
# This file lives in $GIT_COMMON_DIR/hooks, which the primary checkout and every
# linked worktree share. It therefore names no path belonging to any one
# worktree: `uv run --frozen` resolves lefthook from the cwd git sets, which is
# the top level of the worktree whose hook fired. Refs issue #4789.
#
# Rewrite it with: {REPAIR_COMMAND}

if [ "$LEFTHOOK" = "0" ]; then
  exit 0
fi

if [ "$LEFTHOOK_VERBOSE" = "1" ] || [ "$LEFTHOOK_VERBOSE" = "true" ]; then
  set -x
fi

if [ -n "$LEFTHOOK_BIN" ]; then
  exec "$LEFTHOOK_BIN" run "{hook}" "$@"
fi

exec uv run --frozen lefthook run "{hook}" "$@"
"""


def _git(repo_root: Path, *args: str) -> str:
    """Return stdout for a git command, raising :class:`GitQueryError` on failure."""
    git = shutil.which("git")
    if git is None:
        raise GitQueryError("git executable not found")
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            [git, *args],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitQueryError(f"git {' '.join(args)} failed to execute: {exc}") from exc
    if result.returncode != 0:
        raise GitQueryError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def config_path(repo_root: Path) -> Path | None:
    """Return the lefthook config this repository uses, or None when it uses none."""
    for name in LEFTHOOK_CONFIG_NAMES:
        candidate = repo_root / name
        if candidate.is_file():
            return candidate
    return None


def declared_hooks(config: Path) -> list[str]:
    """Return the git hook names the lefthook config declares, in file order.

    Reads top-level mapping keys and keeps only those that name a client-side
    git hook. A key-shaped line inside a block scalar cannot reach this: block
    scalars are indented, and the pattern requires column zero.
    """
    hooks: list[str] = []
    for line in config.read_text(encoding="utf-8").splitlines():
        match = _TOP_LEVEL_KEY.match(line)
        if match is None:
            continue
        key = match.group(1)
        if key in GIT_CLIENT_HOOKS and key not in hooks:
            hooks.append(key)
    return hooks


def hooks_dir(repo_root: Path) -> Path:
    """Return the directory git reads hooks from.

    ``--git-path hooks`` yields a path relative to git's working directory when
    the repository is addressed relatively, so resolve it against ``repo_root``
    rather than the interpreter's cwd.
    """
    raw = _git(repo_root, "rev-parse", "--git-path", "hooks")
    if not raw:
        raise GitQueryError("git returned an empty hooks path")
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def shim_defect(hook: str, path: Path) -> str | None:
    """Return why ``path`` is not a usable worktree-safe shim, or None."""
    if not path.is_file():
        return f"{path} is missing"
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"{path} could not be read as text: {exc}"
    if not os.access(path, os.X_OK):
        return f"{path} is not executable, so git will ignore it"
    if content == hook_shim(hook):
        return None
    if _VENV_PATH.search(content) is not None:
        return (
            f"{path} bakes in an absolute '/.venv/' path, so it names one "
            "checkout's virtual environment and breaks for every other worktree"
        )
    return f"{path} is not the worktree-safe shim for '{hook}'"


def find_defects(repo_root: Path) -> tuple[list[str], int]:
    """Return the shim defects and how many hooks were examined."""
    config = config_path(repo_root)
    if config is None:
        return [], 0
    directory = hooks_dir(repo_root)
    hooks = declared_hooks(config)
    defects = [
        defect
        for hook in hooks
        if (defect := shim_defect(hook, directory / hook)) is not None
    ]
    return defects, len(hooks)


def run_lefthook_install(repo_root: Path) -> None:
    """Run ``lefthook install --reset-hooks-path`` so lefthook records its state.

    Clears any ``core.hooksPath`` override and writes lefthook's config checksum
    to ``$GIT_COMMON_DIR/info/lefthook.checksum``. The shim files it writes here
    are overwritten immediately afterwards; only the bookkeeping is wanted.
    """
    argv = ["uv", "run", "--frozen", "lefthook", "install", "--reset-hooks-path"]
    try:
        result = subprocess.run(
            argv,
            cwd=str(repo_root),
            check=False,
            timeout=_INSTALL_TIMEOUT_SECONDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitQueryError(f"{' '.join(argv)} failed to execute: {exc}") from exc
    if result.stdout:
        print(result.stdout, file=sys.stderr, end="")
    if result.returncode != 0:
        raise GitQueryError(f"{' '.join(argv)} exited {result.returncode}")


def write_shims(repo_root: Path, hooks: list[str]) -> list[Path]:
    """Overwrite each hook file with its worktree-safe shim. Returns what changed."""
    directory = hooks_dir(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for hook in hooks:
        path = directory / hook
        if shim_defect(hook, path) is None:
            continue
        path.write_text(hook_shim(hook), encoding="utf-8")
        path.chmod(_HOOK_MODE)
        written.append(path)
    return written


def _report_check(defects: list[str], examined: int) -> int:
    """Print the --check verdict and return its ADR-035 exit code."""
    if not defects:
        print(f"lefthook shims: OK, {examined} of {examined} examined hooks are worktree-safe")
        return 0
    print(
        f"[FAIL] {len(defects)} of {examined} examined lefthook shims are not worktree-safe:",
        file=sys.stderr,
    )
    for defect in defects:
        print(f"    - {defect}", file=sys.stderr)
    print(f"Fix: {REPAIR_COMMAND}", file=sys.stderr)
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install lefthook hook shims that every worktree can share."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report only: exit non-zero on a divergent shim and mutate nothing.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Worktree to operate on (default: the current worktree).",
    )
    return parser.parse_args(argv)


def _resolve_root(explicit: str | None) -> Path:
    """Return the worktree root to operate on."""
    start = Path(explicit).resolve() if explicit else Path.cwd()
    return Path(_git(start, "rev-parse", "--show-toplevel")).resolve()


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)
    try:
        repo_root = _resolve_root(args.repo_root)
    except GitQueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    config = config_path(repo_root)
    if config is None:
        print(f"error: no lefthook config under {repo_root}", file=sys.stderr)
        return 2

    try:
        if args.check:
            defects, examined = find_defects(repo_root)
            return _report_check(defects, examined)

        run_lefthook_install(repo_root)
        hooks = declared_hooks(config)
        written = write_shims(repo_root, hooks)
        defects, examined = find_defects(repo_root)
    except GitQueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    print(
        f"lefthook shims: rewrote {len(written)} of {examined} examined hooks in "
        f"{hooks_dir(repo_root)}"
    )
    if defects:
        for defect in defects:
            print(f"    - {defect}", file=sys.stderr)
        print("error: shims are still not worktree-safe after the rewrite", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
