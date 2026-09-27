"""Shared repo I/O, target resolution, and glob matching for effective context.

Split out of ``effective_context_resolvers.py`` (issue #4880 CQA/taste-lints
follow-up: the merged module hit 803 lines and triggered the taste-lints
file-size ERROR at 500). This module holds what ``effective_context_claude``
and ``effective_context_copilot`` both need: reading a file live or at a
``git`` rev, listing a directory the same way, resolving a target path to its
directory, parsing a rule/instructions file's frontmatter scope key, and
matching a glob against a target. Harness-specific loading rules live in
their own module.

Layer names both harness resolvers use are a shared vocabulary, not an
observed harness concept:

- ``root``: files loaded once, the same for every target in the repository.
- ``nested``: files loaded because of the target's directory, strictly below
  the repository root. This is the layer the path-local ratchet (REQ-6) sums,
  because it is the layer that can silently regrow per-directory.
- ``scoped``: files whose own frontmatter glob decides whether they apply to
  this specific target.
- ``user``: per-developer files, reported but never in a ratcheted total
  (REQ-5).
"""

from __future__ import annotations

import posixpath
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from scripts.validation.instruction_budget_globs import (
    _ALL_FILES_FORMS,
    _FRONTMATTER_RE,
    UnsupportedApplyToError,
    _glob_to_regex,
    _iter_applyto_globs,
    _UniqueKeySafeLoader,
    _vscode_effective_glob,
)

__all__ = [
    "GitUnavailableError",
    "ImportProblem",
    "InvalidRevError",
    "LoadedFile",
    "Repo",
    "TargetOutsideRepoError",
    "UnsupportedApplyToError",
    "directory_chain",
    "glob_matches",
    "resolve_base_directory",
]


def _decode(data: bytes | str) -> str:
    """Return ``data`` as ``str``, stripped: a git ``stderr`` may be either.

    ``Repo``'s ``git show`` call passes no ``text=True`` (it needs the raw
    bytes of the file on success), so its ``stderr`` on failure is ``bytes``;
    a test double may hand back a plain ``str`` instead. Decoding
    defensively here, once, keeps :meth:`Repo.read_bytes`'s error message
    formatting the same either way.
    """
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace").strip()
    return data.strip()


class InvalidRevError(ValueError):
    """``--rev`` does not name a commit git can resolve."""


class GitUnavailableError(RuntimeError):
    """``git`` is not on PATH, is not a repository here, or a command timed out.

    Moved here from ``effective_context_resolvers`` (issue #4880 post-rebase
    review finding): ``Repo``'s own ``--rev`` accessors now raise it too, so
    the type has to live where ``Repo`` is defined, not in the module that
    imports ``Repo`` from here (importing it back from
    ``effective_context_resolvers`` would be circular).
    ``effective_context_resolvers`` re-exports this name unchanged, so
    ``ecr.GitUnavailableError`` (the existing public import path used by
    ``effective_context.py`` and its tests) still resolves to this exact
    type; :func:`~scripts.validation.effective_context_resolvers.discover_nested_directories`
    raises it too, for the same reason (a broken ``git ls-files`` there).
    """


class TargetOutsideRepoError(ValueError):
    """A ``--target`` (or an import inside a resolved file) escapes the repo.

    Raised by :func:`resolve_base_directory` for the CLI's own ``--target``
    argument (the caller converts this to ADR-035 exit code 2). An import
    inside a file that resolves outside the repository root is a different,
    softer case: :class:`ImportProblem` records it and resolution continues,
    per REQ-4 ("report it and not follow it"), rather than raising.
    """


@dataclass(frozen=True)
class LoadedFile:
    """One file a harness loads for a target, and why."""

    layer: str
    path: str
    size_bytes: int
    reason: str


@dataclass(frozen=True)
class ImportProblem:
    """A ``@`` import that could not be followed (REQ-4).

    ``kind`` is one of ``"cycle"``, ``"missing"``, or ``"outside_repo"``.
    ``location`` is the file containing the import; ``target`` is the raw
    import token as written (including its leading ``@``). Claude-only
    today (Copilot CLI does no ``@`` import expansion), but the type lives
    here, alongside ``LoadedFile``, because both are the shared vocabulary
    :class:`~scripts.validation.effective_context_resolvers.EffectiveContextResult`
    reports for either harness.
    """

    kind: str
    location: str
    target: str


class Repo:
    """Reads repository file bytes and directory listings, live or at a rev.

    ``rev=None`` reads the working tree with :meth:`pathlib.Path.read_bytes`.
    A ``rev`` reads through ``git show REV:path`` and lists directories
    through ``git ls-tree --name-only REV -- dir/`` (argv lists, no shell,
    per the spec's Security section). Both are read-only and cannot write.
    """

    def __init__(self, root: Path, rev: str | None) -> None:
        self._root = root
        self._rev = rev

    def read_bytes(self, rel_path: str) -> bytes | None:
        """Return the file's bytes, or ``None`` if it does not exist at this rev.

        At a ``--rev``, :meth:`_exists_at_rev` decides absence first, so a
        missing path or a directory returns ``None``. A ``git show`` that
        still fails after that probe is a real git error and raises
        :class:`GitUnavailableError` (exit 3 at the CLI), as does a timeout.
        """
        if self._rev is None:
            candidate = self._root / rel_path
            if not candidate.is_file():
                return None
            return candidate.read_bytes()
        if not self._exists_at_rev(rel_path):
            return None
        try:
            result = subprocess.run(
                ["git", "show", f"{self._rev}:{rel_path}"],
                cwd=self._root,
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"git show {self._rev}:{rel_path} timed out in {self._root}: {exc}"
            raise GitUnavailableError(msg) from exc
        if result.returncode != 0:
            stderr = _decode(result.stderr)
            msg = f"git show {self._rev}:{rel_path} exited {result.returncode}: {stderr}"
            raise GitUnavailableError(msg)
        return result.stdout

    def _exists_at_rev(self, rel_path: str) -> bool:
        """True when ``rel_path`` is a blob at ``self._rev`` (``git cat-file -t``).

        The one existence probe :meth:`read_bytes` trusts. A non-zero exit
        means "not present at this rev". A tree (a directory) is also absent,
        because ``git show`` of a tree prints a listing, not file bytes. A
        timeout raises, because a hung probe proves neither presence nor
        absence.
        """
        try:
            result = subprocess.run(
                ["git", "cat-file", "-t", f"{self._rev}:{rel_path}"],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"git cat-file -t {self._rev}:{rel_path} timed out in {self._root}: {exc}"
            raise GitUnavailableError(msg) from exc
        return result.returncode == 0 and result.stdout.strip() == "blob"

    def is_dir(self, rel_path: str) -> bool:
        """True when ``rel_path`` names a directory (repo root if empty)."""
        if not rel_path:
            return True
        if self._rev is None:
            return (self._root / rel_path).is_dir()
        return bool(self._ls_tree(self._rev, rel_path.rstrip("/") + "/"))

    def list_dir(self, rel_dir: str) -> list[str]:
        """Return repo-relative file paths directly inside ``rel_dir``.

        Non-recursive: only the two flat directories the harness resolvers
        read (``.claude/rules``, ``.github/instructions``) call this.
        """
        if self._rev is None:
            directory = self._root / rel_dir
            if not directory.is_dir():
                return []
            return sorted(
                f"{rel_dir}/{entry.name}" for entry in directory.iterdir() if entry.is_file()
            )
        entries = self._ls_tree(self._rev, rel_dir.rstrip("/") + "/")
        return sorted(name for entry_type, name in entries if entry_type == "blob")

    def _ls_tree(self, rev: str, pathspec: str) -> list[tuple[str, str]]:
        """List ``(type, name)`` for every entry directly under ``pathspec`` at ``rev``.

        Deliberately omits ``--name-only``: that flag drops the ``<mode>
        <type> <sha>`` prefix, so a listed name cannot be told apart from a
        same-named subdirectory (a git tree entry). ``list_dir`` keeps only
        ``blob`` entries, matching its live-tree branch, which already
        excludes a subdirectory via ``is_file()``; ``is_dir`` only needs
        non-emptiness (a directory holding nothing but subdirectories is
        still a directory), so it does not filter by type.

        A non-zero exit still yields ``[]`` (a bad rev already fails earlier
        through :meth:`rev_is_valid`, so this method's own contract for a
        git-level failure stays "empty listing", unchanged). Only a timeout
        raises :class:`GitUnavailableError`: a hang is not evidence the
        listing is empty, and letting it escape as an uncaught
        ``subprocess.TimeoutExpired`` would be the same silent-traceback
        shape :meth:`read_bytes` had.
        """
        try:
            result = subprocess.run(
                ["git", "ls-tree", rev, "--", pathspec],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"git ls-tree {rev} -- {pathspec} timed out in {self._root}: {exc}"
            raise GitUnavailableError(msg) from exc
        if result.returncode != 0:
            return []
        entries: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            metadata, _, name = line.partition("\t")
            fields = metadata.split(" ")
            if name and len(fields) >= 2:
                entries.append((fields[1], name))
        return entries

    def rev_is_valid(self) -> bool:
        """True when ``self._rev`` names a commit git can resolve.

        A non-zero exit is ``False`` (an unresolvable rev, unchanged
        contract); only a timeout raises :class:`GitUnavailableError`,
        matching :meth:`_ls_tree`'s reasoning.
        """
        if self._rev is None:
            return True
        if self._rev.startswith("-"):
            return False
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"{self._rev}^{{commit}}"],
                cwd=self._root,
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"git rev-parse --verify {self._rev} timed out in {self._root}: {exc}"
            raise GitUnavailableError(msg) from exc
        return result.returncode == 0


def resolve_base_directory(repo: Repo, target: str) -> str:
    """Return the target's directory, repo-relative POSIX, ``""`` for root.

    A target that is an existing directory (in the working tree, or in the
    tree at the rev ``repo`` was constructed with) resolves to itself. Otherwise it resolves to its
    parent, whether or not the file exists there yet (a ``--rev`` target may
    not exist at that commit). Raises :class:`TargetOutsideRepoError` for an
    absolute path or one that escapes the repository root through ``..``.
    """
    normalized = posixpath.normpath(target.replace("\\", "/"))
    if PurePosixPath(normalized).is_absolute() or normalized.split("/")[0] == "..":
        raise TargetOutsideRepoError(target)
    if normalized == ".":
        normalized = ""
    if repo.is_dir(normalized):
        return normalized
    parent = posixpath.dirname(normalized)
    return parent


def directory_chain(base_dir: str) -> list[str]:
    """Directories strictly below the repo root, root-to-target, inclusive.

    ``""`` (a target at the repo root) yields an empty chain: there is no
    directory strictly below root to hold a nested file.
    """
    if not base_dir:
        return []
    parts = base_dir.split("/")
    return ["/".join(parts[: index + 1]) for index in range(len(parts))]


def parse_scope_patterns(text: str, key: str) -> set[str] | None:
    """Return the glob set under ``key`` in frontmatter, or ``None`` if absent.

    ``None`` means the file carries no such key at all, which both loading
    models treat as "always loaded" (no scoping). Reuses
    ``instruction_budget_globs``'s frontmatter YAML loader (duplicate-key
    fail-closed) and its ``str``-or-``list``-of-``str`` flattener
    (``_iter_applyto_globs``), so a ``paths:`` key is parsed with the exact
    same shape rules as ``applyTo:``, rather than a second implementation.
    Raises ``UnsupportedApplyToError`` on malformed YAML, a duplicate
    top-level key, or a value that is neither a string nor a list of strings.
    """
    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match is None:
        return None
    try:
        data = yaml.load(fm_match.group(1), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        msg = f"frontmatter is not valid YAML: {exc}"
        raise UnsupportedApplyToError(msg) from exc
    if not isinstance(data, dict) or key not in data:
        return None
    return {p.strip() for p in _iter_applyto_globs(data[key]) if p.strip()}


def glob_matches(patterns: set[str], target_path: str) -> bool:
    """True if any glob in ``patterns`` matches ``target_path``.

    Reuses ``instruction_budget_globs``'s VS Code-faithful glob compiler
    (``_vscode_effective_glob`` then ``_glob_to_regex``), the same matcher the
    instruction-budget gate uses for Copilot ``applyTo:``. This module also
    uses it for Claude Code's ``paths:`` frontmatter.

    Divergence risk (documented, not verified this session): VS Code's
    matcher prepends ``**/`` to any pattern that is not already absolute or
    ``**/``-anchored, so an unprefixed ``paths:`` entry such as
    ``scripts/validation/**`` (seen in ``ci-scripts.md``) matches a
    same-named subtree anywhere in the repo, not only one anchored at the
    repo root. No probe of Claude Code's own ``paths:`` matcher exists in
    this repository to confirm or refute that it anchors differently; reusing
    the VS Code matcher is the documented choice from the task, not an
    observed fact about Claude Code's glob dialect.
    """
    probe = "/" + target_path.lstrip("/")
    for pattern in patterns:
        effective = _vscode_effective_glob(pattern)
        if effective in _ALL_FILES_FORMS:
            return True
        if _glob_to_regex(effective).match(probe):
            return True
    return False
