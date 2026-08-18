#!/usr/bin/env python3
"""Gate: local pushes have an executable ``pre-push`` hook.

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

Detection starts with one path-resolution call. ``git rev-parse --git-path
hooks`` returns the directory git will actually read: it honors ``core.hooksPath`` (absolute or
relative), and in a linked worktree it resolves to the common directory's
``hooks/`` rather than ``.git/worktrees/<name>/hooks``, which is where lefthook
installs and where a worktree push really looks. Verified on git 2.51.0
against a scratch repository with a linked worktree: a marker pre-push under
the common directory fired on a push from the worktree, and stopped firing
once removed. So ``--git-common-dir`` is unnecessary, and the whole health
test is whether ``<git-path hooks>/pre-push`` is an executable file, which
also covers the "directory exists but holds no pre-push" and "hook exists but
Git will ignore it" cases. ``core.hooksPath`` is read only on the unhealthy
path, to name which condition failed.

Scope: the remedy is a lefthook command, so this gate passes silently in any
repository that does not configure lefthook. A repository with no hooks and no
lefthook config has chosen that, and is not broken. CI also skips this
local-clone check because workflows invoke validation directly without
installing the checkout's local ``pre-push`` hook.

Exit codes (ADR-035):
    0 - Success (hooks live, or the question does not apply here)
    1 - Logic error (git will run no hook)
    2 - Config error (invalid repository root)
    3 - External failure (git missing, timed out, or failed unexpectedly)

An explicit non-repository is out of scope and exits 0. Missing git, timeouts,
and unexpected command failures are verification failures and exit 3; the
pre-PR adapter receives False for the same states.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# The repair below is a lefthook command, so this gate only speaks to a
# repository that configures lefthook. These are the config names lefthook
# itself looks for.
LEFTHOOK_CONFIG_NAMES = tuple(
    f"{stem}{local}.{extension}"
    for stem in ("lefthook", ".lefthook", ".config/lefthook")
    for local in ("", "-local")
    for extension in ("yml", "yaml", "json", "jsonc", "toml")
)

# pre-push is the probe because it is the last gate before a branch reaches
# the remote, and lefthook installs it alongside every other shim: its absence
# means the install never ran or was overridden.
PROBE_HOOK = "pre-push"

REMEDY = "uv run --frozen lefthook install --reset-hooks-path"
WORKTREE_REMEDY = f"git config --worktree --unset-all core.hooksPath && {REMEDY}"
GLOBAL_REMEDY = f"git config --global --unset-all core.hooksPath && {REMEDY}"
SYSTEM_REMEDY = f"git config --system --unset-all core.hooksPath && {REMEDY}"

# A hung git must not stall the pre-PR run. A local rev-parse answers in
# milliseconds, so this only trips on a genuine hang. The gate fails closed
# with ADR-035 exit 3 because an unreadable hook state is not a verified pass.
GIT_TIMEOUT_SECONDS = 5


class GitExecutionError(RuntimeError):
    """Git was unavailable or failed before the gate could establish a fact."""


class NotGitRepositoryError(RuntimeError):
    """The target is explicitly outside a Git work tree."""


def _git(repo_root: Path, *args: str, missing_ok: bool = False) -> str | None:
    """Return stdout, preserving non-repository and execution failures distinctly."""
    git = shutil.which("git")
    if git is None:
        raise GitExecutionError("git executable not found")
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
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitExecutionError(f"git command failed to execute: {exc}") from exc
    if result.returncode == 0:
        return result.stdout.strip()
    if missing_ok and result.returncode == 1:
        return None
    if "not a git repository" in result.stderr.lower():
        raise NotGitRepositoryError(result.stderr.strip())
    raise GitExecutionError(
        f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
    )


def _uses_lefthook(repo_root: Path) -> bool:
    return any((repo_root / name).is_file() for name in LEFTHOOK_CONFIG_NAMES)


def _hooks_dir(repo_root: Path) -> Path:
    """Return the directory git reads hooks from or raise a typed failure.

    ``--git-path hooks`` yields a path relative to git's working directory
    when the repository is addressed relatively, so resolve it against the
    repository root rather than the interpreter's cwd.
    """
    raw = _git(repo_root, "rev-parse", "--git-path", "hooks")
    if not raw:
        raise GitExecutionError("git returned an empty hooks path")
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path


def _configured_hooks_path(repo_root: Path) -> tuple[str | None, str | None]:
    """Return the effective ``core.hooksPath`` value and its config scope."""
    value = _git(
        repo_root, "config", "--get", "core.hooksPath", missing_ok=True
    ) or None
    scoped = _git(
        repo_root,
        "config",
        "--show-scope",
        "--get",
        "core.hooksPath",
        missing_ok=True,
    )
    if value is None or scoped is None:
        return value, None
    scope, separator, scoped_value = scoped.partition("\t")
    if not separator or scoped_value != value:
        return value, None
    return value, scope


def _remedy(repo_root: Path) -> str:
    """Return a repair that clears the authoritative hooks-path scope."""
    _configured, scope = _configured_hooks_path(repo_root)
    if scope == "worktree":
        return WORKTREE_REMEDY
    if scope == "global":
        return GLOBAL_REMEDY
    if scope == "system":
        return SYSTEM_REMEDY
    if scope == "command":
        return f"remove the command-scoped core.hooksPath override; then run: {REMEDY}"
    return REMEDY


def _failed_condition(repo_root: Path, hooks_dir: Path) -> str:
    """Describe why git will not run pre-push. Called only on the unhealthy path."""
    hook = hooks_dir / PROBE_HOOK
    if hook.is_file():
        return f"{hook} exists but is not executable, so git will ignore it"

    configured, scope = _configured_hooks_path(repo_root)
    if configured is None:
        return f"{hook} is missing and core.hooksPath is unset"
    scope_text = f" in {scope} scope" if scope is not None else ""
    if not hooks_dir.is_dir():
        return (
            f"core.hooksPath is set to '{configured}'{scope_text} "
            "and that directory does not exist"
        )
    return (
        f"core.hooksPath is set to '{configured}'{scope_text} "
        f"but that directory has no {PROBE_HOOK} hook"
    )


def _diagnose_hooks_dir(repo_root: Path, hooks_dir: Path) -> str | None:
    """Diagnose the already-resolved hooks directory without querying git again."""
    hook = hooks_dir / PROBE_HOOK
    if hook.is_file() and os.access(hook, os.X_OK):
        return None
    return _failed_condition(repo_root, hooks_dir)


def diagnose(repo_root: Path) -> str | None:
    """Return the failed condition, or None when healthy or out of scope."""
    if not _uses_lefthook(repo_root):
        return None
    try:
        hooks_dir = _hooks_dir(repo_root)
    except NotGitRepositoryError:
        return None
    return _diagnose_hooks_dir(repo_root, hooks_dir)


def _evaluate(repo_root: Path) -> int:
    """Evaluate once and return the ADR-035 exit code."""
    if (
        os.environ.get("GITHUB_ACTIONS", "").lower() in ("true", "1")
        or os.environ.get("CI", "").lower() in ("true", "1")
    ):
        print("git hook health: skipped under CI (0 hooks probed)")
        return 0
    if not _uses_lefthook(repo_root):
        print(
            "git hook health: skipped, no lefthook config in "
            f"{repo_root} (0 hooks probed)"
        )
        return 0

    try:
        hooks_dir = _hooks_dir(repo_root)
        reason = _diagnose_hooks_dir(repo_root, hooks_dir)
        remedy = _remedy(repo_root) if reason is not None else None
    except NotGitRepositoryError:
        print(
            f"git hook health: skipped, {repo_root} is not a git repository "
            "(0 hooks probed)"
        )
        return 0
    except GitExecutionError as exc:
        print(f"[ERROR] Git hook health could not be verified: {exc}", file=sys.stderr)
        return 3

    if reason is None:
        print(
            f"git hook health: {PROBE_HOOK} present in {hooks_dir} "
            "(1 of 1 probed hook found)"
        )
        return 0

    print(f"[FAIL] {reason}.", file=sys.stderr)
    print(
        "Pushes are not locally gated: pre-push does not run.",
        file=sys.stderr,
    )
    print(f"Fix: {remedy}", file=sys.stderr)
    return 1


def validate_git_hook_health(repo_root: Path) -> bool:
    """Return False when pre-push is inert or verification is impossible.

    Entry point matching the contract the pre-PR registry consumes. Canonical
    source: ``scripts/validation/pre_pr_sequence.py:150``, whose adapter
    signature reads verbatim (quoted at column 0 so the 96-character original
    is reproduced byte for byte rather than wrapped to fit an indent):

def _root_only(validator: Callable[[Path], bool]) -> Callable[[Path, argparse.Namespace], bool]:

    A dead pre-push hook or an unverifiable Git state fails loud rather than
    warning. The repair is bounded, and refusing an unverifiable push avoids
    silently recreating the incident this gate exists to catch
    (.claude/rules/ci-scripts.md MUST 11).

    Prints what was probed and where it resolved on the healthy path, so a
    caller can tell "checked and found hooks live" from "did nothing"
    (.claude/rules/ci-scripts.md MUST 12). The silence-when-healthy contract
    of the original SessionStart design does not apply here: that output landed
    in every session's context, this lands in one pre-PR report.
    """
    return _evaluate(repo_root) == 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return _evaluate(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
