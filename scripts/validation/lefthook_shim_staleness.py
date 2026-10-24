#!/usr/bin/env python3
"""Detect Lefthook shims older than the configured ``lefthook:`` runner key.

Split out of ``check_git_hook_health`` because it answers a separate question:
that gate asks whether git reaches Lefthook, this asks whether the shim reaches
the repository's own runner. Issue #6896.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

# A shim that dispatches Lefthook but never reaches the configured ``lefthook:``
# command. It leads its own diagnosis so the summary names the real gap: the
# hook runs, and the repository's runner does not.
STALE_SHIM_PREFIX = "stale Lefthook shim: "
STALE_SHIM_SUMMARY = (
    "Git runs these hooks, but they skip the repository's Lefthook runner, "
    "so checks it adds, such as the pre-push file list, do not run."
)


def runner_branches(runner: str) -> tuple[tuple[str, str, str], ...]:
    """The three-line branch Lefthook renders for the configured ``lefthook:`` command.

    The template emits ``elif test -n "<command>"``, ``then``, and
    ``<command> "$@"``. Matching the whole branch matters: the shim also carries
    built-in fallbacks such as ``uv run lefthook "$@"``, so a bare invocation
    line would accept a stale shim whenever the configured command equals one
    of them (issue #6896). A shim generated before the
    key existed lacks the branch, and one generated against another value
    carries that value's branch instead. Lines are compared whole and stripped,
    so a comment that quotes the command does not satisfy it.

    ``lefthook dump`` prints the value as written, and the installer rewrites
    it before embedding it (measured on Lefthook 2.2.2): it trims the value and
    joins the lines of a multi-line value with ``;``. On Windows it also turns
    backslashes into slashes. A healthy shim would otherwise read as stale, and
    the printed repair would regenerate the same shim, an unfixable failure. So
    both the joined form and its slash form are accepted.
    """
    joined = ";".join(runner.strip().splitlines())
    forms = {joined, joined.replace(chr(92), "/")}
    return tuple((f'elif test -n "{form}"', "then", f'{form} "$@"') for form in sorted(forms))


def runner_failure(hook: Path, runner: str) -> bool:
    """True when ``hook`` never invokes the configured ``lefthook:`` command.

    An unreadable file counts as stale: ``_dispatch_failure`` already read it
    successfully moments earlier, so a failure here is a race, and an
    unverifiable shim is not a verified pass. The check proves the generated
    branch is present, which is what a stale generated shim lacks. It does not
    prove the branch is reachable in a hand-edited shim.
    """
    try:
        lines = [line.strip() for line in hook.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError):
        return True
    windows = list(zip(lines, lines[1:], lines[2:], strict=False))
    return not any(branch in windows for branch in runner_branches(runner))


def stale_shims(
    hooks_dir: Path,
    hook_names: frozenset[str],
    runner: str | None,
    is_live: Callable[[Path, str], bool],
) -> str | None:
    """Report live shims that skip the configured ``lefthook:`` runner.

    Lefthook embeds the key's value in each shim when it installs. With
    ``no_auto_install: true`` nothing refreshes a shim after the key lands, so
    a clone installed earlier keeps calling Lefthook directly and the runner,
    including the pre-push file list it builds (issue #6884), never executes.
    The dispatch-line check passes such a shim because the dispatch line is
    the same in every Lefthook version. Hooks that are absent or inert are
    left to ``_missing_hook_types``, which owns that diagnosis.
    """
    if runner is None:
        return None
    stale = sorted(
        name
        for name in hook_names
        if is_live(hooks_dir / name, name) and runner_failure(hooks_dir / name, runner)
    )
    if not stale:
        return None
    return (
        f"{STALE_SHIM_PREFIX}{hooks_dir} holds {'shims' if len(stale) > 1 else 'a shim'} for "
        f"{', '.join(stale)} that never call the configured lefthook command '{runner}', "
        "so git runs Lefthook directly and skips the repository runner"
    )
