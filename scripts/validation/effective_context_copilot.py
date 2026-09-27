"""Copilot CLI's effective-context resolution: root, nested, scoped, user.

Split out of ``effective_context_resolvers.py`` (issue #4880 CQA/taste-lints
follow-up; see ``effective_context_sources`` module docstring for why).
Everything here is specific to Copilot CLI's own loading model: no ``@``
import expansion (not observed for Copilot CLI either way, see the module
docstring in ``_runtime_harness.py``), so this resolver counts raw bytes
only, and ``.github/instructions/*.instructions.md`` ``applyTo`` scoping.
"""

from __future__ import annotations

import os
from pathlib import Path

from scripts.validation.effective_context_sources import (
    LoadedFile,
    Repo,
    directory_chain,
    glob_matches,
    parse_scope_patterns,
)

__all__ = [
    "all_copilot_instructions",
    "copilot_static_paths_unfiltered",
    "resolve_copilot",
]

COPILOT_INSTRUCTIONS_DIR = ".github/instructions"
COPILOT_REPO_INSTRUCTIONS = ".github/copilot-instructions.md"
COPILOT_HOME_ENV = "COPILOT_HOME"
COPILOT_HOME_DEFAULT = ".copilot"
COPILOT_HOME_FILE = "copilot-instructions.md"


def all_copilot_instructions(repo: Repo) -> list[str]:
    """Every ``.github/instructions/*.instructions.md`` file, unfiltered.

    Used both to build the scoped layer (after an ``applyTo`` filter) and, by
    ``--observe``, as half of the "static set before the applyTo filter"
    comparison (REQ-3): Copilot's own ``instruction list`` enumerates every
    instructions file regardless of ``applyTo``, applying the filter only at
    edit time.
    """
    return [
        rel_path
        for rel_path in repo.list_dir(COPILOT_INSTRUCTIONS_DIR)
        if rel_path.endswith(".instructions.md")
    ]


def copilot_static_paths_unfiltered(repo: Repo, base_dir: str) -> set[str]:
    """Every repository file Copilot CLI's own listing would enumerate.

    Used by ``--observe`` (REQ-3) as the "before the applyTo filter" half of
    its comparison: root/nested files that exist, unioned with every
    ``.github/instructions/*.instructions.md`` file regardless of whether its
    ``applyTo`` matches this target.
    """
    paths: set[str] = set()
    if repo.read_bytes(COPILOT_REPO_INSTRUCTIONS) is not None:
        paths.add(COPILOT_REPO_INSTRUCTIONS)
    for name in ("AGENTS.md", "CLAUDE.md"):
        if repo.read_bytes(name) is not None:
            paths.add(name)
    for directory in directory_chain(base_dir):
        for name in ("AGENTS.md", "CLAUDE.md"):
            rel_path = f"{directory}/{name}"
            if repo.read_bytes(rel_path) is not None:
                paths.add(rel_path)
    paths.update(all_copilot_instructions(repo))
    return paths


def _copilot_root_files(repo: Repo) -> list[LoadedFile]:
    """``.github/copilot-instructions.md`` plus repo-root ``AGENTS.md``/``CLAUDE.md``."""
    files: list[LoadedFile] = []
    root_bytes = repo.read_bytes(COPILOT_REPO_INSTRUCTIONS)
    if root_bytes is not None:
        files.append(LoadedFile("root", COPILOT_REPO_INSTRUCTIONS, len(root_bytes), "root file"))
    for name in ("AGENTS.md", "CLAUDE.md"):
        data = repo.read_bytes(name)
        if data is not None:
            files.append(LoadedFile("root", name, len(data), "root file"))
    return files


def _copilot_nested_files(repo: Repo, base_dir: str) -> list[LoadedFile]:
    """``AGENTS.md``/``CLAUDE.md`` in each directory strictly below the repo root."""
    files: list[LoadedFile] = []
    for directory in directory_chain(base_dir):
        for name in ("AGENTS.md", "CLAUDE.md"):
            rel_path = f"{directory}/{name}"
            data = repo.read_bytes(rel_path)
            if data is not None:
                files.append(LoadedFile("nested", rel_path, len(data), "nested file"))
    return files


def _copilot_scoped_files(repo: Repo, target: str) -> list[LoadedFile]:
    """``.github/instructions/*.instructions.md`` whose ``applyTo`` matches ``target``.

    No repository instructions file omits `applyTo` today (verified: zero of
    27 `.github/instructions/*.instructions.md` files lack it). Absent an
    observed case, a missing key scopes the file to nothing, matching
    `instruction_budget_globs.parse_applyto`'s empty-set return for the same
    shape, which the existing budget gate already treats as non-universal.
    This is a documented assumption, not a probed fact about Copilot CLI.
    """
    files: list[LoadedFile] = []
    for rel_path in all_copilot_instructions(repo):
        data = repo.read_bytes(rel_path)
        if data is None:
            continue
        text = data.decode("utf-8", errors="replace")
        patterns = parse_scope_patterns(text, "applyTo")
        if patterns is None:
            continue
        if glob_matches(patterns, target):
            files.append(LoadedFile("scoped", rel_path, len(data), "applyTo: matches target"))
    return files


def _copilot_user_file(include_user: bool) -> list[LoadedFile]:
    """``$COPILOT_HOME/copilot-instructions.md``, default ``~/.copilot/...``."""
    if not include_user:
        return []
    home = Path(os.environ.get(COPILOT_HOME_ENV) or (Path.home() / COPILOT_HOME_DEFAULT))
    user_path = home / COPILOT_HOME_FILE
    if not user_path.is_file():
        return []
    data = user_path.read_bytes()
    return [LoadedFile("user", str(user_path), len(data), "user file")]


def resolve_copilot(
    repo: Repo,
    base_dir: str,
    target: str,
    *,
    include_user: bool,
) -> list[LoadedFile]:
    """Return the files Copilot CLI loads for ``target``.

    Root: ``.github/copilot-instructions.md``, plus ``AGENTS.md`` and
    ``CLAUDE.md`` at the repo root. Nested: ``AGENTS.md`` and ``CLAUDE.md`` in
    each directory strictly below the repo root down to ``base_dir``. No
    ``@`` import expansion: not observed for Copilot CLI either way (see the
    module docstring in ``_runtime_harness.py``), so this resolver counts raw
    bytes only. Scoped: ``.github/instructions/*.instructions.md`` whose
    ``applyTo`` matches ``target``. User (only with ``include_user``):
    ``$COPILOT_HOME/copilot-instructions.md``, default
    ``~/.copilot/copilot-instructions.md``.

    Root and nested here are this resolver's own split, not a distinction
    Copilot's own loading model draws (it treats "repo root" as just the
    first directory in one root-to-target chain). The split exists so the
    path-local ratchet (REQ-6), which sums the ``nested`` layer only, does
    not double-count the root ``AGENTS.md``/``CLAUDE.md`` bytes that are
    identical for every target as if they were per-directory growth.

    Each layer is built by its own helper (``_copilot_root_files`` and
    siblings) so this function is a flat concatenation, not a branch tree.
    """
    return [
        *_copilot_root_files(repo),
        *_copilot_nested_files(repo, base_dir),
        *_copilot_scoped_files(repo, target),
        *_copilot_user_file(include_user),
    ]
