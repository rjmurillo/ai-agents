#!/usr/bin/env python3
"""Gate: git is configured to run no hooks at all.

A git hook cannot detect its own absence. When ``core.hooksPath`` names a
directory that does not exist, git runs no hook and prints no warning, and
``.git/hooks/`` is ignored entirely. Every pre-commit, commit-msg,
pre-merge-commit, and pre-push hook is then silently inert, in the main
checkout and in every linked worktree, which share one config.

Measured cost: this repository sat in that state, so the generated-file
hand-edit on PR #5059 reached CI instead of being refused at push time by the
``build-all-check`` pre-push job. It is not a one-time slip either.
``.agents/sessions/2026-07-19-session-3182-githooks-activation.json`` records
the same repair on 2026-07-19, after which the setting drifted back. A
condition that recurs needs detection, not another manual fix. Issue #5090.

Why this runs in ``pre_pr.py`` rather than at session start: dead hooks matter
most immediately before a push, which is exactly when this gate runs, and
``AGENTS.md`` names ``pre_pr.py`` the pre-PR gate.

Detection is one git call. ``git rev-parse --git-path hooks`` returns the
directory git will actually read: it honors ``core.hooksPath`` (absolute or
relative), and in a linked worktree it resolves to the common directory's
``hooks/`` rather than ``.git/worktrees/<name>/hooks``, which is where lefthook
installs and where a worktree push really looks. Verified on git 2.51.0
against a scratch repository with a linked worktree: a marker pre-push under
the common directory fired on a push from the worktree, and stopped firing
once removed. So ``--git-common-dir`` is unnecessary, and the whole health
test is whether ``<git-path hooks>/pre-push`` is a file, which also covers the
"directory exists but holds no pre-push" case. ``core.hooksPath`` is read only
on the unhealthy path, to name which condition failed.

Scope: the remedy is a lefthook command, so this gate passes silently in any
repository that does not configure lefthook. A repository with no hooks and no
lefthook config has chosen that, and is not broken.

Exit codes (ADR-035):
    0 - Success (hooks live, or the question does not apply here)
    1 - Logic error (git will run no hook)
    2 - Config error (invalid repository root)

Indeterminate states exit 0 on purpose: no git binary, not a git repository,
or a git call that times out. This gate reports a fact it can establish, and
a state it cannot read is not evidence that hooks are dead.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# The repair below is a lefthook command, so this gate only speaks to a
# repository that configures lefthook. These are the config names lefthook
# itself looks for.
LEFTHOOK_CONFIG_NAMES = (
    "lefthook.yml",
    "lefthook.yaml",
    ".lefthook.yml",
    ".lefthook.yaml",
    "lefthook.toml",
    "lefthook.json",
)

# pre-push is the probe because it is the last gate before a branch reaches
# the remote, and lefthook installs it alongside every other shim: its absence
# means the install never ran or was overridden.
PROBE_HOOK = "pre-push"

REMEDY = "uv run --frozen lefthook install --reset-hooks-path"

# A hung git must not stall the pre-PR run. A local rev-parse answers in
# milliseconds, so this only trips on a genuine hang, where degrading to a
# pass is the right move: a timeout is not evidence that hooks are dead.
GIT_TIMEOUT_SECONDS = 5


def _git(repo_root: Path, *args: str) -> str | None:
    """Return stripped stdout of a git command, or None when it cannot run."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [git, *args],
            cwd=str(repo_root),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _uses_lefthook(repo_root: Path) -> bool:
    return any((repo_root / name).is_file() for name in LEFTHOOK_CONFIG_NAMES)


def _hooks_dir(repo_root: Path) -> Path | None:
    """Return the directory git reads hooks from, or None when undeterminable.

    ``--git-path hooks`` yields a path relative to git's working directory
    when the repository is addressed relatively, so resolve it against the
    repository root rather than the interpreter's cwd.
    """
    raw = _git(repo_root, "rev-parse", "--git-path", "hooks")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path


def _configured_hooks_path(repo_root: Path) -> str | None:
    """Return the ``core.hooksPath`` value, or None when it is unset."""
    return _git(repo_root, "config", "--get", "core.hooksPath") or None


def _failed_condition(repo_root: Path, hooks_dir: Path) -> str:
    """Describe why git will run no hook. Called only on the unhealthy path."""
    configured = _configured_hooks_path(repo_root)
    if configured is None:
        return f"{hooks_dir / PROBE_HOOK} is missing and core.hooksPath is unset"
    if not hooks_dir.is_dir():
        return (
            f"core.hooksPath is set to '{configured}' "
            "and that directory does not exist"
        )
    return (
        f"core.hooksPath is set to '{configured}' "
        f"but that directory has no {PROBE_HOOK} hook"
    )


def diagnose(repo_root: Path) -> str | None:
    """Return the failed-condition text, or None when hooks are healthy.

    Returns None for every case this gate has nothing useful to say about: a
    repository without lefthook, a directory that is not a git repository, and
    a git that cannot be run at all.
    """
    if not _uses_lefthook(repo_root):
        return None
    hooks_dir = _hooks_dir(repo_root)
    if hooks_dir is None:
        return None
    if (hooks_dir / PROBE_HOOK).is_file():
        return None
    return _failed_condition(repo_root, hooks_dir)


def validate_git_hook_health(repo_root: Path) -> bool:
    """Return True when git will run hooks, False when every hook is inert.

    Entry point matching the contract the pre-PR registry consumes. Canonical
    source: ``scripts/validation/pre_pr_sequence.py:147``, whose adapter
    signature reads verbatim (quoted at column 0 so the 96-character original
    is reproduced byte for byte rather than wrapped to fit an indent):

def _root_only(validator: Callable[[Path], bool]) -> Callable[[Path, argparse.Namespace], bool]:

    Fails loud rather than warning. Dead hooks mean the push ahead of this run
    is not gated at all, and the repair is one documented command, so blocking
    costs the contributor seconds and saves a round in CI
    (.claude/rules/ci-scripts.md MUST 11).

    Prints what was probed and where it resolved on the healthy path, so a
    caller can tell "checked and found hooks live" from "did nothing"
    (.claude/rules/ci-scripts.md MUST 12). The silence-when-healthy contract
    of the original SessionStart design does not apply here: that output landed
    in every session's context, this lands in one pre-PR report.
    """
    if not _uses_lefthook(repo_root):
        print(
            "git hook health: skipped, no lefthook config in "
            f"{repo_root} (0 hooks probed)"
        )
        return True

    hooks_dir = _hooks_dir(repo_root)
    if hooks_dir is None:
        print(
            "git hook health: skipped, git could not report a hooks path "
            "(0 hooks probed)"
        )
        return True

    reason = diagnose(repo_root)
    if reason is None:
        print(
            f"git hook health: {PROBE_HOOK} present in {hooks_dir} "
            "(1 of 1 probed hook found)"
        )
        return True

    print(f"[FAIL] {reason}.", file=sys.stderr)
    print(
        "Every git hook is inert: pre-commit, commit-msg, pre-merge-commit, "
        "and pre-push do not run.",
        file=sys.stderr,
    )
    print(f"Fix: {REMEDY}", file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_git_hook_health(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
