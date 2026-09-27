"""Per-harness resolvers for path-local effective instruction context.

Encodes the loading model observed on the maintainer's machine for two CLIs
(SPEC-4880, issue #4880). Each resolver returns the files a harness loads for
one target path, tagged by layer, plus any :class:`ImportProblem` found while
following Claude Code ``@`` imports.

Layer names are shared across harnesses so a report table reads the same way
for both, but what each layer means differs by harness (see each resolver's
docstring): the shared name is the resolver's own choice, not an observed
harness concept:

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

import os
import posixpath
import re
import subprocess
from collections.abc import Callable
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

MAX_IMPORT_DEPTH = 5

CLAUDE_RULES_DIR = ".claude/rules"
COPILOT_INSTRUCTIONS_DIR = ".github/instructions"
COPILOT_REPO_INSTRUCTIONS = ".github/copilot-instructions.md"
COPILOT_HOME_ENV = "COPILOT_HOME"
COPILOT_HOME_DEFAULT = ".copilot"
COPILOT_HOME_FILE = "copilot-instructions.md"
CLAUDE_USER_ROOT = ".claude/CLAUDE.md"


class InvalidRevError(ValueError):
    """``--rev`` does not name a commit git can resolve."""


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
    import token as written (including its leading ``@``).
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
        self.root = root
        self.rev = rev

    def read_bytes(self, rel_path: str) -> bytes | None:
        """Return the file's bytes, or ``None`` if it does not exist."""
        if self.rev is None:
            candidate = self.root / rel_path
            if not candidate.is_file():
                return None
            return candidate.read_bytes()
        result = subprocess.run(
            ["git", "show", f"{self.rev}:{rel_path}"],
            cwd=self.root,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def is_dir(self, rel_path: str) -> bool:
        """True when ``rel_path`` names a directory (repo root if empty)."""
        if not rel_path:
            return True
        if self.rev is None:
            return (self.root / rel_path).is_dir()
        return bool(self._ls_tree(self.rev, rel_path.rstrip("/") + "/"))

    def list_dir(self, rel_dir: str) -> list[str]:
        """Return repo-relative file paths directly inside ``rel_dir``.

        Non-recursive: only the two flat directories this module reads
        (``.claude/rules``, ``.github/instructions``) call this.
        """
        if self.rev is None:
            directory = self.root / rel_dir
            if not directory.is_dir():
                return []
            return sorted(
                f"{rel_dir}/{entry.name}" for entry in directory.iterdir() if entry.is_file()
            )
        return sorted(self._ls_tree(self.rev, rel_dir.rstrip("/") + "/"))

    def _ls_tree(self, rev: str, pathspec: str) -> list[str]:
        result = subprocess.run(
            ["git", "ls-tree", "--name-only", rev, "--", pathspec],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line]

    def rev_is_valid(self) -> bool:
        """True when ``self.rev`` names a commit git can resolve."""
        if self.rev is None:
            return True
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{self.rev}^{{commit}}"],
            cwd=self.root,
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0


def resolve_base_directory(repo: Repo, target: str) -> str:
    """Return the target's directory, repo-relative POSIX, ``""`` for root.

    A target that is an existing directory (in the working tree, or in the
    tree at ``repo.rev``) resolves to itself. Otherwise it resolves to its
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


_FENCE_MARKER = "```"


def extract_import_tokens(text: str) -> list[str]:
    """Return each ``@import`` token that occupies its own line.

    Matches the form observed in every root/nested ``CLAUDE.md`` in this
    repository (``CLAUDE.md``, ``.github/CLAUDE.md``, ``scripts/CLAUDE.md``:
    each has ``@AGENTS.md`` alone on its own line). A whole-line match
    naturally excludes an import mentioned inside inline code (a backtick
    opens the line, so ``^@`` cannot match) without a separate inline-code
    scanner. Lines inside a triple-backtick fence are skipped by toggling on
    any line whose stripped form starts with ``` (a language tag after the
    fence, e.g. ```python, does not change this: the toggle only cares that
    the line starts with the fence marker).

    Stricter than "anywhere in the line": an ``@import`` embedded mid-sentence
    is not recognized. No file in this repository does that; if one starts
    to, this resolver would under-count rather than over-count, which is the
    safe direction for a budget gate reused by a ratchet (REQ-6).
    """
    tokens: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_FENCE_MARKER):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("@") and " " not in stripped and "\t" not in stripped:
            tokens.append(stripped)
    return tokens


def _resolve_relative_import(base_dir: str, raw_token: str) -> str:
    joined = posixpath.join(base_dir, raw_token) if base_dir else raw_token
    return posixpath.normpath(joined)


def _process_relative_import(
    raw: str,
    rel_path: str,
    ancestors: tuple[str, ...],
    active_read: Callable[[str], bytes | None],
    active_layer: str,
    seen: set[str],
    problems: list[ImportProblem],
    files: list[LoadedFile],
) -> tuple[str, bytes] | None:
    """Resolve one project-relative ``@import`` token.

    Returns ``(candidate_path, candidate_bytes)`` to recurse into, or
    ``None`` when the import escaped the repo, is a cycle, is missing, or was
    already billed (each case is handled here so :func:`walk_claude_imports`
    only has to branch on "recurse or not").
    """
    base_dir = posixpath.dirname(rel_path)
    candidate = _resolve_relative_import(base_dir, raw[1:])
    if candidate.startswith("..") or PurePosixPath(candidate).is_absolute():
        problems.append(ImportProblem("outside_repo", rel_path, raw))
        return None
    if candidate in ancestors:
        problems.append(ImportProblem("cycle", rel_path, raw))
        return None
    data = active_read(candidate)
    if data is None:
        problems.append(ImportProblem("missing", rel_path, raw))
        return None
    if candidate in seen:
        return None
    seen.add(candidate)
    files.append(
        LoadedFile(
            layer=active_layer,
            path=candidate,
            size_bytes=len(data),
            reason=f"import via {rel_path}",
        )
    )
    return candidate, data


def _process_tilde_import(
    raw: str,
    rel_path: str,
    seen: set[str],
    problems: list[ImportProblem],
    files: list[LoadedFile],
    tilde_read: Callable[[str], bytes | None] | None,
) -> tuple[str, bytes] | None:
    """Resolve one ``@~/...`` token against the user's home directory.

    Returns ``(key, candidate_bytes)`` (``key`` is ``~/``-prefixed) to
    recurse into, or ``None`` when ``tilde_read`` is unset (``--include-user``
    was not passed), the file is missing, or it was already billed.
    """
    if tilde_read is None:
        return None
    home_rel = raw[3:]
    key = f"~/{home_rel}"
    if key in seen:
        return None
    data = tilde_read(home_rel)
    if data is None:
        problems.append(ImportProblem("missing", rel_path, raw))
        return None
    seen.add(key)
    files.append(
        LoadedFile(layer="user", path=key, size_bytes=len(data), reason=f"import via {rel_path}")
    )
    return key, data


def walk_claude_imports(
    read_bytes: Callable[[str], bytes | None],
    start_rel: str,
    start_content: bytes,
    layer: str,
    seen: set[str],
    problems: list[ImportProblem],
    files: list[LoadedFile],
    *,
    tilde_read: Callable[[str], bytes | None] | None,
) -> None:
    """Follow ``@`` imports from ``start_content``, appending discovered files.

    ``seen`` is shared with the caller across every root and nested file in
    one resolution, so a file imported from two places is billed once.
    Project-relative paths are keyed by their own POSIX path; a ``@~/...``
    token is keyed with a ``~/`` prefix so it cannot collide with a
    project path of the same spelling. ``tilde_read`` resolves a ``~/...``
    token against the user's home directory; passing ``None`` means
    ``--include-user`` was not set, so such a token is left unfollowed and is
    not reported as a problem (it is a valid, known construct, just not one
    this run chose to resolve).

    The starting file is depth 0 (not itself an import). A file reached
    through :data:`MAX_IMPORT_DEPTH` hops (depth 5) is still read and
    reported, matching the "max depth 5" observed loading model, but its own
    imports are never read: the chain is capped at 5 hops from the start
    file, not 5 files total. A cycle is a revisit of an ancestor in the
    *current* import chain, not merely a file seen anywhere before;
    re-reaching an already-resolved file through a second, non-cyclic path
    is silently deduplicated via ``seen`` instead of reported as a problem.

    Per-token resolution lives in :func:`_process_relative_import` and
    :func:`_process_tilde_import`; this function only decides whether to
    recurse into what they resolve, keeping its own branching (and mccabe
    complexity) to the recursion shape alone.
    """

    def _follow(
        rel_path: str,
        content: bytes,
        depth: int,
        ancestors: tuple[str, ...],
        active_read: Callable[[str], bytes | None],
        active_layer: str,
    ) -> None:
        if depth >= MAX_IMPORT_DEPTH:
            return
        text = content.decode("utf-8", errors="replace")
        for raw in extract_import_tokens(text):
            if raw.startswith("@~/"):
                resolved = _process_tilde_import(raw, rel_path, seen, problems, files, tilde_read)
                if resolved is not None:
                    assert tilde_read is not None  # _process_tilde_import returns None otherwise
                    key, data = resolved
                    _follow(key, data, depth + 1, (key,), tilde_read, "user")
                continue
            resolved_relative = _process_relative_import(
                raw, rel_path, ancestors, active_read, active_layer, seen, problems, files
            )
            if resolved_relative is not None:
                candidate, data = resolved_relative
                _follow(
                    candidate, data, depth + 1, (*ancestors, candidate), active_read, active_layer
                )

    _follow(start_rel, start_content, 0, (start_rel,), read_bytes, layer)


def _home_read(home: Path, rel_path: str) -> bytes | None:
    candidate = home / rel_path
    if not candidate.is_file():
        return None
    return candidate.read_bytes()


def resolve_claude(
    repo: Repo,
    base_dir: str,
    target: str,
    *,
    include_user: bool,
) -> tuple[list[LoadedFile], list[ImportProblem]]:
    """Return the files Claude Code loads for ``target``, and any problems.

    Root: ``CLAUDE.md`` and ``.claude/CLAUDE.md`` at the repo root, plus their
    ``@`` imports. Nested: ``CLAUDE.md`` in each directory strictly below the
    repo root down to ``base_dir``, plus imports. Scoped:
    ``.claude/rules/*.md`` whose frontmatter ``paths:`` matches ``target``, or
    that carries no ``paths:`` key at all (always loaded). User (only with
    ``include_user``): ``~/.claude/CLAUDE.md`` plus imports, read live off
    disk regardless of ``repo.rev`` because user config is not versioned.
    """
    seen: set[str] = set()
    files: list[LoadedFile] = []
    problems: list[ImportProblem] = []
    tilde_read = (lambda rel: _home_read(Path.home(), rel)) if include_user else None

    for root_path in ("CLAUDE.md", ".claude/CLAUDE.md"):
        _add_and_walk(repo.read_bytes, root_path, "root", seen, files, problems, tilde_read)

    for directory in directory_chain(base_dir):
        _add_and_walk(
            repo.read_bytes, f"{directory}/CLAUDE.md", "nested", seen, files, problems, tilde_read
        )

    files.extend(_resolve_claude_scoped(repo, target))

    if include_user:
        home_bytes = _home_read(Path.home(), "CLAUDE.md")
        if home_bytes is not None:
            key = "~/CLAUDE.md"
            seen.add(key)
            files.append(
                LoadedFile(
                    layer="user", path=key, size_bytes=len(home_bytes), reason="user root file"
                )
            )
            walk_claude_imports(
                lambda rel: _home_read(Path.home(), rel),
                "CLAUDE.md",
                home_bytes,
                "user",
                seen,
                problems,
                files,
                tilde_read=tilde_read,
            )

    return files, problems


def _add_and_walk(
    read_bytes: Callable[[str], bytes | None],
    rel_path: str,
    layer: str,
    seen: set[str],
    files: list[LoadedFile],
    problems: list[ImportProblem],
    tilde_read: Callable[[str], bytes | None] | None,
) -> None:
    """Add ``rel_path`` if it exists and is unseen, then follow its imports."""
    if rel_path in seen:
        return
    data = read_bytes(rel_path)
    if data is None:
        return
    seen.add(rel_path)
    files.append(
        LoadedFile(layer=layer, path=rel_path, size_bytes=len(data), reason=f"{layer} file")
    )
    walk_claude_imports(
        read_bytes, rel_path, data, layer, seen, problems, files, tilde_read=tilde_read
    )


def _parse_scope_patterns(text: str, key: str) -> set[str] | None:
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


def _resolve_claude_scoped(repo: Repo, target: str) -> list[LoadedFile]:
    files: list[LoadedFile] = []
    for rel_path in repo.list_dir(CLAUDE_RULES_DIR):
        data = repo.read_bytes(rel_path)
        if data is None:
            continue
        text = data.decode("utf-8", errors="replace")
        patterns = _parse_scope_patterns(text, "paths")
        if patterns is None:
            reason = "no paths: key (always loaded)"
        elif glob_matches(patterns, target):
            reason = "paths: matches target"
        else:
            continue
        files.append(LoadedFile(layer="scoped", path=rel_path, size_bytes=len(data), reason=reason))
    return files


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
        patterns = _parse_scope_patterns(text, "applyTo")
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
    automatically.

    Working tree only, via ``git ls-files`` (no ``--rev``): this backs
    ``--ci``, which always checks the working tree, matching
    :data:`CEILINGS_BYTES`'s own frozen-target loop. The repository root is
    excluded (it is the ``root`` layer, not ``nested``); an untracked file is
    invisible, matching every other resolver in this module, which reads
    repository content, not the working tree's scratch files; a path under a
    fixture-tree segment is excluded and returned separately so the caller
    can report what it skipped and why.

    Returns ``([], [])`` when ``repo_root`` is not a git repository (or
    ``git`` is unavailable), rather than raising: discovery degrades to "no
    extra directories found," and the five frozen targets still ratchet.
    """
    result = subprocess.run(
        ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return [], []
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
