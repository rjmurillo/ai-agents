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
once removed. So ``--git-common-dir`` is unnecessary, and the health test is
whether ``<git-path hooks>/pre-push`` is an executable file that dispatches
Lefthook, which also covers the "directory exists but holds no pre-push" and
"hook exists but Git will ignore it" cases. ``core.hooksPath`` is read only on
the unhealthy path, to name which condition failed.

Executability alone is not installation evidence. ``#!/bin/sh`` followed by
``exit 0`` is an executable ``pre-push`` that runs no job, so a clone in that
state passes an executability-only probe while every local guardrail is off.
The adjacent ``Lefthook Installed`` gate cannot cover the difference either: it
proves the configured runtime starts, not that git will reach it. So this gate
reads the hook and requires Lefthook's own dispatch line (issue #4789).

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

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import tomllib
import yaml

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

# Lefthook's generated shim ends by dispatching the hook through its own
# resolver function, and that line is the one part of the template every
# supported platform shares. Measured on the shim Lefthook 2.1.11 installed
# into this repository: the last line is `call_lefthook run "pre-commit" "$@"`.
# `tests/test_lefthook_integration.py::test_install_resets_legacy_hooks_path`
# asserts the same line for the Windows template, which differs from the POSIX
# one everywhere else: it omits the configured runner, the `LEFTHOOK_BIN`
# override, and the PATH fallback. Matching this instead of parsing the shim
# keeps the gate on Lefthook's own output rather than reimplementing a shell
# reader, which the ADR-086 amendment debate rejected.
DISPATCH_MARKER = f'call_lefthook run "{PROBE_HOOK}"'
# The complete generated command, matched exactly. A containment test on the
# final line still accepts `echo 'call_lefthook run "pre-push"'`, which is an
# executable final command that dispatches nothing (CWE-693). Including `"$@"`
# also pins argument forwarding, which the Windows template asserts separately
# in `tests/test_lefthook_integration.py`.
DISPATCH_COMMAND = f'{DISPATCH_MARKER} "$@"'

# Every git hook Lefthook can install. Used to tell hook types apart from the
# settings that share the config's top level (`min_version`, `lefthook`,
# `no_auto_install`, `glob_matcher`).
# Identifies the missing-hook-type diagnosis so the summary line below does not
# claim pre-push is dead when pre-push is what proved live.
_MISSING_TYPES_PREFIX = "has no live shim for configured hook"

# Read from the JSON schema Lefthook 2.1.11 embeds in its own binary, not from
# memory: the hand-written version omitted nine names, and a hook type this set
# does not know is silently dropped and never checked for a shim.
GIT_HOOK_NAMES = frozenset(
    "applypatch-msg commit-msg fsmonitor-watchman p4-changelist p4-post-changelist "
    "p4-pre-submit p4-prepare-changelist post-applypatch post-checkout post-commit "
    "post-index-change post-merge post-receive post-rewrite post-update pre-applypatch "
    "pre-auto-gc pre-commit pre-merge-commit pre-push pre-rebase pre-receive "
    "prepare-commit-msg proc-receive push-to-checkout reference-transaction "
    "sendemail-validate update".split()
)


def _dispatch_command(hook_name: str) -> str:
    """The complete line Lefthook generates as ``hook_name``'s final command."""
    return f'call_lefthook run "{hook_name}" "$@"'

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
    if not hooks_dir.exists():
        return (
            f"core.hooksPath is set to '{configured}'{scope_text} "
            "and that directory does not exist"
        )
    if not hooks_dir.is_dir():
        return (
            f"core.hooksPath is set to '{configured}'{scope_text} "
            "and that path exists but is not a directory"
        )
    return (
        f"core.hooksPath is set to '{configured}'{scope_text} "
        f"but that directory has no {PROBE_HOOK} hook"
    )


def _final_command(text: str) -> str:
    """Return the last line that a shell would execute, ignoring comments.

    Not a shell parser: the ADR-086 amendment debate rejected one. This reads
    the last non-blank, non-comment line, which is where Lefthook's generated
    shim puts its dispatch on every platform.
    """
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _dispatch_failure(hook: Path, hook_name: str) -> str | None:
    """Return why ``hook`` does not dispatch Lefthook, or None when it does.

    The final command must equal the generated dispatch, not contain it. Two
    weaker versions of this check were fail-open in the same way (CWE-693, PR
    #5358 review). A whole-file substring accepts an inert hook mentioning the
    marker in a comment above ``exit 0``. A containment test on the final line
    accepts ``echo 'call_lefthook run "pre-push"'``. Both are executable, both
    report healthy, and neither runs a guard.

    A read failure is reported separately from a wrong command. Collapsing them
    into one boolean made the caller say the final command was wrong when no
    command had been read, hiding the permission or I/O fault behind a
    misleading diagnosis. Both still fail the gate: an unverifiable hook is not
    a verified pass.
    """
    try:
        text = hook.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"{hook} could not be read ({exc}), so its state is unverifiable"
    if _final_command(text) != _dispatch_command(hook_name):
        return (
            f"{hook} is executable but does not dispatch Lefthook: its final "
            f"command is not exactly '{_dispatch_command(hook_name)}', so git "
            "runs no repository guardrail"
        )
    return None


def _parse_hook_types(path: Path) -> frozenset[str] | None:
    """Hook types declared in one config file, or None when unreadable."""
    name = path.name
    try:
        raw = path.read_bytes()
        if name.endswith((".yml", ".yaml")):
            data = yaml.safe_load(raw.decode("utf-8"))
        elif name.endswith(".json"):
            data = json.loads(raw)
        elif name.endswith(".toml"):
            data = tomllib.loads(raw.decode("utf-8"))
        else:
            return None
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    return frozenset(str(key) for key in data) & GIT_HOOK_NAMES


def _configured_hook_types(repo_root: Path) -> frozenset[str] | None:
    """Hook types declared across every Lefthook config, or None if unreadable.

    Every config file is read, not the first match. ``LEFTHOOK_CONFIG_NAMES``
    includes the ``-local`` overlays, and a local file that adds a hook type
    installs a shim for it, so stopping at the base file reports healthy while
    the overlay's hook type has none.

    The union is the safe direction here. This gate asks which hook types could
    be installed, not which jobs win a merge, and a type present in any config
    needs a shim.

    Returns None rather than an empty set when any config cannot be parsed, so
    the caller keeps the single-probe behavior instead of reporting every hook
    type as missing. ``.jsonc`` has no stdlib parser and lands there.
    """
    found: set[str] = set()
    seen_any = False
    for name in LEFTHOOK_CONFIG_NAMES:
        path = repo_root / name
        if not path.is_file():
            continue
        seen_any = True
        parsed = _parse_hook_types(path)
        if parsed is None:
            return None
        found |= parsed
    return frozenset(found) if seen_any else None


def _diagnose_hooks_dir(repo_root: Path, hooks_dir: Path) -> str | None:
    """Diagnose the already-resolved hooks directory without querying git again."""
    hook = hooks_dir / PROBE_HOOK
    if not (hook.is_file() and os.access(hook, os.X_OK)):
        return _failed_condition(repo_root, hooks_dir)
    probe_failure = _dispatch_failure(hook, PROBE_HOOK)
    if probe_failure is not None:
        return probe_failure
    return _missing_hook_types(repo_root, hooks_dir)


def _is_live_hook(hook: Path, hook_name: str) -> bool:
    """True when git will run ``hook`` and it dispatches Lefthook.

    Both halves, in the same order the ``pre-push`` probe applies them. Text
    alone is not enough: on POSIX a shim carrying the exact dispatch line at
    mode 0644 is ignored by git.
    """
    if not (hook.is_file() and os.access(hook, os.X_OK)):
        return False
    return _dispatch_failure(hook, hook_name) is None


def _missing_hook_types(repo_root: Path, hooks_dir: Path) -> str | None:
    """Report configured hook types whose shim is absent or does not dispatch.

    ``no_auto_install: true`` stops one worktree re-syncing the shims every
    other worktree reads (issue #4789), and the same setting means a newly
    configured hook type keeps no shim until install runs again. Git runs no
    hook it has no file for and prints no warning, so probing ``pre-push``
    alone reports healthy while the hook type someone just added is inert.
    """
    configured = _configured_hook_types(repo_root)
    if configured is None:
        return None
    missing = sorted(
        name
        for name in configured - {PROBE_HOOK}
        if not _is_live_hook(hooks_dir / name, name)
    )
    if not missing:
        return None
    return (
        f"{hooks_dir} {_MISSING_TYPES_PREFIX} "
        f"{'types' if len(missing) > 1 else 'type'} {', '.join(missing)}, so "
        "git runs nothing for them; run install again after any hook-type change"
    )


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
        probed = sorted((_configured_hook_types(repo_root) or frozenset()) | {PROBE_HOOK})
        names, count = ", ".join(probed), len(probed)
        print(f"git hook health: {names} live in {hooks_dir} ({count} of {count} found)")
        return 0

    print(f"[FAIL] {reason}.", file=sys.stderr)
    # Only claim the push is ungated when the pre-push probe is what failed.
    # A missing commit-msg shim reaches here with a working pre-push, and the
    # blanket line sent contributors after the wrong hook.
    if _MISSING_TYPES_PREFIX in reason:
        print(
            "Those hook types run nothing locally. pre-push itself is live.",
            file=sys.stderr,
        )
    else:
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
