"""Orchestrates per-harness effective-context resolution (SPEC-4880, #4880).

``resolve_effective_context`` is the one entry point ``effective_context.py``
(the CLI) calls: it dispatches to :mod:`effective_context_claude` or
:mod:`effective_context_copilot` and wraps the result in
:class:`EffectiveContextResult`, which derives the three totals the CLI and
the ratchet report.

This module used to hold every resolver directly (803 lines, over the
taste-lints 500-line ERROR threshold). It now re-exports the split modules'
public names so ``effective_context.py`` and existing tests keep importing
from one place; see ``effective_context_sources``, ``effective_context_claude``,
and ``effective_context_copilot`` for the resolution logic itself.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.effective_context_claude import (
    _add_and_walk as _add_and_walk,
)
from scripts.validation.effective_context_claude import (
    _ImportSink as _ImportSink,
)
from scripts.validation.effective_context_claude import (
    _resolve_claude_scoped as _resolve_claude_scoped,
)
from scripts.validation.effective_context_claude import (
    extract_import_tokens as extract_import_tokens,
)
from scripts.validation.effective_context_claude import (
    resolve_claude,
)
from scripts.validation.effective_context_copilot import (
    COPILOT_HOME_ENV as COPILOT_HOME_ENV,
)
from scripts.validation.effective_context_copilot import (
    all_copilot_instructions as all_copilot_instructions,
)
from scripts.validation.effective_context_copilot import (
    copilot_static_paths_unfiltered as copilot_static_paths_unfiltered,
)
from scripts.validation.effective_context_copilot import (
    resolve_copilot,
)
from scripts.validation.effective_context_sources import (
    GitUnavailableError as GitUnavailableError,
)
from scripts.validation.effective_context_sources import (
    ImportProblem as ImportProblem,
)
from scripts.validation.effective_context_sources import (
    InvalidRevError,
    Repo,
    resolve_base_directory,
)
from scripts.validation.effective_context_sources import (
    LoadedFile as LoadedFile,
)
from scripts.validation.effective_context_sources import (
    TargetOutsideRepoError as TargetOutsideRepoError,
)
from scripts.validation.effective_context_sources import (
    directory_chain as directory_chain,
)
from scripts.validation.effective_context_sources import (
    glob_matches as glob_matches,
)

__all__ = [
    "COPILOT_HOME_ENV",
    "EffectiveContextResult",
    "GitUnavailableError",
    "ImportProblem",
    "InvalidRevError",
    "LoadedFile",
    "Repo",
    "TargetOutsideRepoError",
    "all_copilot_instructions",
    "copilot_static_paths_unfiltered",
    "directory_chain",
    "discover_nested_directories",
    "extract_import_tokens",
    "glob_matches",
    "resolve_base_directory",
    "resolve_claude",
    "resolve_copilot",
    "resolve_effective_context",
]


@dataclass(frozen=True)
class EffectiveContextResult:
    """One harness's resolved file set for one target, with derived totals.

    ``path_local_bytes`` sums the ``nested`` layer only (REQ-6's ratcheted
    quantity, matching the spec's frozen-targets table, which names only
    nested ``AGENTS.md``/``CLAUDE.md`` files as "local layer under test").
    ``repo_total_bytes`` sums every non-user layer (root, nested, scoped).
    ``user_total_bytes`` is reported but excluded from both other totals and
    from any ratchet (REQ-5).
    """

    target: str
    harness: str
    files: tuple[LoadedFile, ...]
    problems: tuple[ImportProblem, ...]

    @property
    def repo_total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files if f.layer != "user")

    @property
    def path_local_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files if f.layer == "nested")

    @property
    def user_total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files if f.layer == "user")


def resolve_effective_context(
    repo_root: Path,
    target: str,
    harness: str,
    *,
    rev: str | None = None,
    include_user: bool = False,
) -> EffectiveContextResult:
    """Resolve the effective instruction context for one harness and target.

    Raises :class:`TargetOutsideRepoError` for a target escaping the repo, and
    :class:`InvalidRevError` for a ``rev`` git cannot resolve to a commit.
    """
    repo = Repo(repo_root, rev)
    if rev is not None and not repo.rev_is_valid():
        raise InvalidRevError(rev)
    base_dir = resolve_base_directory(repo, target)
    if harness == "claude":
        files, problems = resolve_claude(repo, base_dir, target, include_user=include_user)
    elif harness == "copilot":
        files = resolve_copilot(repo, base_dir, target, include_user=include_user)
        problems = []
    else:
        msg = f"unknown harness {harness!r}; expected 'claude' or 'copilot'"
        raise ValueError(msg)
    return EffectiveContextResult(
        target=target, harness=harness, files=tuple(files), problems=tuple(problems)
    )


# Path segments that mark a fixture tree (issue #4880 AC7's "skip paths under
# tests/**/fixtures/ or other fixture trees"). Matched case-insensitively
# against every path segment, not just under `tests/`, so a fixture tree
# anywhere in the repo is excluded, not only the one location the AC names as
# an example. As of this module's first commit, zero of this repository's
# `CLAUDE.md`/`AGENTS.md` files sit under such a segment (verified: `git
# ls-files | grep -E '(^|/)(CLAUDE|AGENTS)\.md$' | grep -iE 'fixture'`
# returns nothing), so the exclusion excludes zero paths today; it exists so
# a future fixture tree cannot be ratcheted as if it were real instruction
# content.
_FIXTURE_SEGMENT_NAMES = frozenset({"fixtures", "fixture"})

_NESTED_INSTRUCTION_FILE_RE = re.compile(r"(^|/)(CLAUDE|AGENTS)\.md$")


def _is_fixture_path(rel_path: str) -> bool:
    """True when any path segment is a fixture-tree marker, case-insensitive."""
    return any(part.lower() in _FIXTURE_SEGMENT_NAMES for part in rel_path.split("/"))


def discover_nested_directories(repo_root: Path) -> tuple[list[str], list[str]]:
    """Every git-tracked directory with a nested ``CLAUDE.md``/``AGENTS.md``.

    Backs issue #4880 AC7: the five frozen targets alone cannot catch growth
    in a directory none of them happens to pass through (``.agents/``,
    ``.claude/skills/``, a brand-new nested file elsewhere). This discovers
    every such directory instead of naming them, so a new one is covered
    automatically. Lives in this orchestrator module, not
    ``effective_context_sources``, because it is a ratchet-facing directory
    finder that neither ``resolve_claude`` nor ``resolve_copilot`` consumes,
    unlike everything ``effective_context_sources`` holds.

    Working tree only, via ``git ls-files`` (no ``--rev``): this backs
    ``--ci``, which always checks the working tree, matching
    ``CEILINGS_BYTES``'s own frozen-target loop. The repository root is
    excluded (it is the ``root`` layer, not ``nested``); an untracked file is
    invisible, matching every resolver in this package, which reads
    repository content, not the working tree's scratch files; a path under a
    fixture-tree segment is excluded and returned separately so the caller
    can report what it skipped and why.

    Raises :class:`GitUnavailableError` (ADR-035 exit code 3) when ``git
    ls-files`` fails or times out, rather than returning ``([], [])``: an
    empty result the caller cannot tell apart from "no directories found"
    would let :func:`~scripts.validation.effective_context.check_directory_ceiling`
    pass with zero directories checked, reporting the ratchet green while it
    never ran.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        msg = f"git ls-files failed to run in {repo_root}: {exc}"
        raise GitUnavailableError(msg) from exc
    if result.returncode != 0:
        msg = f"git ls-files exited {result.returncode} in {repo_root}: {result.stderr.strip()}"
        raise GitUnavailableError(msg)
    directories: set[str] = set()
    excluded: list[str] = []
    for line in result.stdout.splitlines():
        rel_path = line.strip()
        if not rel_path or not _NESTED_INSTRUCTION_FILE_RE.search(rel_path):
            continue
        directory = posixpath.dirname(rel_path)
        if not directory:
            continue
        if _is_fixture_path(directory):
            excluded.append(rel_path)
            continue
        directories.add(directory)
    return sorted(directories), sorted(excluded)
