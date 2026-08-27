"""What the repo-health gate tells the reader, and the verdict it says it about.

Split from ``check_repo_health.py`` so that file stays under the 500-line taste
ceiling, but the seam is a real one: this module decides nothing and reads no
git, and that file spawns no output. Issue #4698 is a diagnosis problem before
it is a detection problem. The corruption surfaced as four unrelated-looking
failures and drew three wrong diagnoses, so what the gate prints is the whole
deliverable and deserves to be readable and testable on its own.

Every line goes to the stream its severity belongs on: a verdict the reader must
act on to stderr, an all-clear to stdout. Each all-clear carries the number of
config scopes actually read, so "nothing is wrong" cannot be confused with
"nothing was examined" (`.claude/rules/ci-scripts.md` MUST-12).

Stricter/looser/different than canonical: `.agents/governance/GOTCHAS.md` names
one repair, quoted verbatim from its "Repair" and "Immunize" lines::

    git config core.bare false

    git config --worktree core.bare false          # in the main checkout
    git -C <each linked worktree> config --worktree core.bare false

That first command writes to the local config and cannot clear a
worktree-scoped, global, or system value, so `_SCOPE_REPAIRS` below names one
repair per scope that carries the value. The immunization line is added only
when `extensions.worktreeConfig` is enabled: measured on git 2.43.0,
`git config --worktree` otherwise exits 128 with `--worktree cannot be used
with multiple working trees unless the config extension worktreeConfig is
enabled`, so printing it unconditionally hands the reader a failing command.

Refs #4698.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_SCOPE_REPAIRS = {
    "worktree": "git config --worktree core.bare false",
    "local": "git config core.bare false",
    "global": "git config --global --unset-all core.bare",
    "system": "git config --system --unset-all core.bare",
    "command": (
        "remove the command-scoped core.bare override "
        "(git -c core.bare=..., GIT_CONFIG_PARAMETERS, or GIT_CONFIG_KEY_n)"
    ),
}
_DEFAULT_REPAIR = _SCOPE_REPAIRS["local"]

_IMMUNIZATION = "git config --worktree core.bare false"

_WORK_TREE_FATAL = "fatal: this operation must be run in a work tree"


@dataclass(frozen=True, slots=True)
class RepoHealth:
    """One health verdict for one repository."""

    status: str
    work_tree: Path | None = None
    bare_scopes: tuple[tuple[str, str], ...] = ()
    scopes_read: int = 0
    effective_bare: bool = False
    worktree_config: bool = False
    # A `true` a later scope overrides, reported so a usable verdict names it
    # instead of the flat "none set true" that would misdescribe the config.
    masked_scopes: tuple[tuple[str, str], ...] = ()


def _repair_lines(health: RepoHealth) -> list[str]:
    """One repair per scope that carries the value, plus the immunization."""
    lines = [
        _SCOPE_REPAIRS.get(scope, _DEFAULT_REPAIR) for scope, _value in health.bare_scopes
    ]
    if health.worktree_config and not any(
        scope == "worktree" for scope, _value in health.bare_scopes
    ):
        lines.append(f"{_IMMUNIZATION}   (in every worktree, so a later flip cannot break it)")
    return lines


def report_corruption(health: RepoHealth) -> None:
    """Name the condition, its blast radius, and a repair per poisoned scope."""
    scopes = ", ".join(f"{scope}={value}" for scope, value in health.bare_scopes)
    print(
        f"[FAIL] core.bare is set true ({scopes}) for a repository whose work "
        f"tree is {health.work_tree}.",
        file=sys.stderr,
    )
    print(f"Every git command needing a work tree fails with: {_WORK_TREE_FATAL}.", file=sys.stderr)
    if not health.effective_bare:
        print(
            "This worktree still resolves usable, so the damage is in a config "
            "it overrides: any worktree without that override is already broken.",
            file=sys.stderr,
        )
    for line in _repair_lines(health):
        print(f"Fix: {line}", file=sys.stderr)
    print(
        "A push can write this value, so a rejected push is not by itself "
        "evidence that the branch is bad. Refs issue #4698 and "
        ".agents/governance/GOTCHAS.md.",
        file=sys.stderr,
    )


def report_unreadable(repo_root: Path, detail: str) -> None:
    """Report a core.bare value git cannot parse, which no git command can clear."""
    print(f"[FAIL] {repo_root} has an unusable core.bare value: {detail}", file=sys.stderr)
    print(
        "git refuses every command in this repository, `git config --unset-all "
        "core.bare` included, so edit the core.bare line out of the config file "
        "by hand. Refs issue #4698.",
        file=sys.stderr,
    )


def report_unverifiable(detail: str) -> None:
    """Report a state the gate could not read, which is not a verified pass."""
    print(f"[ERROR] Repository health could not be verified: {detail}", file=sys.stderr)


def report_usable(repo_root: Path, health: RepoHealth) -> None:
    """Say what was read, and name any true a later scope overrode."""
    masked = ", ".join(f"{scope}={value}" for scope, value in health.masked_scopes)
    detail = f"{masked} overridden by a later scope" if masked else "none set true"
    print(
        f"repo health: core.bare read in {health.scopes_read} config scope(s), "
        f"{detail}, for {repo_root}"
    )


def report_bare_by_design(repo_root: Path, health: RepoHealth) -> None:
    """Say the value is correct here, and never print a repair for it."""
    print(
        f"repo health: skipped, {repo_root} belongs to a bare repository "
        f"with no work tree ({len(health.bare_scopes)} of "
        f"{health.scopes_read} read scope(s) bare by design)"
    )


def report_not_a_repository(repo_root: Path) -> None:
    """Say nothing was examined, explicitly, rather than reporting an all-clear."""
    print(f"repo health: skipped, {repo_root} is not a git repository (0 scopes read)")


def report_invalid_root(repo_root: Path) -> None:
    """Report a root the caller named that is not a directory."""
    print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
