"""Claude Code's effective-context resolution: root, nested, scoped, user.

Split out of ``effective_context_resolvers.py`` (issue #4880 CQA/taste-lints
follow-up; see ``effective_context_sources`` module docstring for why).
Everything here is specific to Claude Code's own loading model: ``@`` import
following (Copilot CLI does none), and ``.claude/rules/*.md`` ``paths:``
scoping.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from scripts.validation.effective_context_sources import (
    ImportProblem,
    LoadedFile,
    Repo,
    directory_chain,
    glob_matches,
    parse_scope_patterns,
)

__all__ = ["resolve_claude"]

# "recurse, max depth 5" from the observed loading model: the starting file is
# depth 0, and a file reached through this many hops is still read, but its
# own imports are never read (see `walk_claude_imports`).
MAX_IMPORT_DEPTH = 5

CLAUDE_RULES_DIR = ".claude/rules"

_FENCE_MARKER = "```"

# An inline code span (`` `...` ``) is stripped before matching, so an
# example like `` `@foo.md` `` in prose is never read as a real import.
_INLINE_CODE_RE = re.compile(r"`[^`]*`")

# `@path` anywhere in a line, not only a whole line to itself: Claude Code
# expands the token wherever it appears ("See @README for details" imports
# `README` exactly as a standalone `@README` line would). The negative
# lookbehind for a preceding word character excludes an email address's `@`
# (`a@b.c`: the `@` is preceded by `a`), since a real import token is never
# glued to the end of another word. `[\w./~-]+` covers the path characters
# this repository's own imports use (letters, digits, `.`, `/`, `~`, `-`).
_IMPORT_TOKEN_RE = re.compile(r"(?<!\w)@[\w./~-]+")


def extract_import_tokens(text: str) -> list[str]:
    """Return each ``@import`` token anywhere in a line, outside code.

    A triple-backtick fence toggles a skip on any line whose stripped form
    starts with it (a language tag after the fence does not change this);
    an inline code span is stripped from the remaining line before matching.

    Broader than an earlier whole-line-only match: Claude Code expands an
    ``@path`` token wherever it appears in a line, so under-counting a
    mid-sentence import was itself a gap, not a safe direction. The
    remaining risk runs the other way now: a ``@``-prefixed token that reads
    like a path but Claude Code would not actually expand (for example a
    social-media handle) would be over-counted. No such token appears in
    this repository's own instruction files.
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
        visible = _INLINE_CODE_RE.sub("", line)
        tokens.extend(_IMPORT_TOKEN_RE.findall(visible))
    return tokens


def _resolve_relative_import(base_dir: str, raw_token: str) -> str:
    joined = posixpath.join(base_dir, raw_token) if base_dir else raw_token
    return posixpath.normpath(joined)


@dataclass
class _ImportSink:
    """Mutable state one Claude import walk threads through every helper.

    Bundles what stays the same across an entire ``walk_claude_imports``
    recursion (``seen``, ``problems``, ``files``, ``tilde_read``) behind one
    parameter, instead of each helper repeating all four in its own
    signature. Not frozen: every field is mutated in place as imports
    resolve. ``tilde_read`` resolves a ``~/...`` token against the user's
    home directory; ``None`` means ``--include-user`` was not set.
    """

    seen: set[str] = field(default_factory=set)
    problems: list[ImportProblem] = field(default_factory=list)
    files: list[LoadedFile] = field(default_factory=list)
    tilde_read: Callable[[str], bytes | None] | None = None


def _process_relative_import(
    raw: str,
    rel_path: str,
    ancestors: tuple[str, ...],
    active_read: Callable[[str], bytes | None],
    active_layer: str,
    sink: _ImportSink,
) -> tuple[str, bytes] | None:
    """Resolve one relative ``@import`` token, project- or home-rooted.

    Returns ``(candidate_path, candidate_bytes)`` to recurse into, or
    ``None`` when the import escaped its root, is a cycle, is missing, or was
    already billed (each case is handled here so :func:`walk_claude_imports`
    only has to branch on "recurse or not").

    ``rel_path`` starting with ``~/`` means the current file is itself
    home-rooted (reached via a ``@~/...`` token): the ``~/`` prefix is
    stripped before computing the directory to join against, so a relative
    import inside ``~/.claude/CLAUDE.md`` resolves under ``~/.claude/``, not
    a literal ``<home>/~/...`` path (``active_read`` in that case is
    ``sink.tilde_read``, which reads relative to the real home directory and
    would fail on a literal ``~`` segment). The ``~/`` prefix is restored on
    the returned candidate, so ``sink.seen`` keeps using the same ``~/``-keyed
    form a project file's direct ``@~/...`` import uses, and the recursive
    caller (:func:`walk_claude_imports`) re-detects ``is_home`` correctly one
    level deeper.
    """
    is_home = rel_path.startswith("~/")
    base_dir = posixpath.dirname(rel_path[len("~/") :] if is_home else rel_path)
    joined = _resolve_relative_import(base_dir, raw[1:])
    if joined.startswith("..") or PurePosixPath(joined).is_absolute():
        sink.problems.append(ImportProblem("outside_repo", rel_path, raw))
        return None
    candidate = f"~/{joined}" if is_home else joined
    if candidate in ancestors:
        sink.problems.append(ImportProblem("cycle", rel_path, raw))
        return None
    data = active_read(joined)
    if data is None:
        sink.problems.append(ImportProblem("missing", rel_path, raw))
        return None
    if candidate in sink.seen:
        return None
    sink.seen.add(candidate)
    sink.files.append(LoadedFile(active_layer, candidate, len(data), f"import via {rel_path}"))
    return candidate, data


def _process_tilde_import(raw: str, rel_path: str, sink: _ImportSink) -> tuple[str, bytes] | None:
    """Resolve one ``@~/...`` token against the user's home directory.

    Returns ``(key, candidate_bytes)`` (``key`` is ``~/``-prefixed) to
    recurse into, or ``None`` when ``sink.tilde_read`` is unset
    (``--include-user`` was not passed), the file is missing, or it was
    already billed.
    """
    if sink.tilde_read is None:
        return None
    home_rel = raw[3:]
    key = f"~/{home_rel}"
    if key in sink.seen:
        return None
    data = sink.tilde_read(home_rel)
    if data is None:
        sink.problems.append(ImportProblem("missing", rel_path, raw))
        return None
    sink.seen.add(key)
    sink.files.append(LoadedFile("user", key, len(data), f"import via {rel_path}"))
    return key, data


def walk_claude_imports(
    read_bytes: Callable[[str], bytes | None],
    start_rel: str,
    start_content: bytes,
    layer: str,
    sink: _ImportSink,
) -> None:
    """Follow ``@`` imports from ``start_content``, appending discovered files.

    ``sink.seen`` is shared across every root/nested file in one resolution,
    so a file imported twice is billed once. A project path is keyed by its
    own POSIX path; a ``@~/...`` token is keyed ``~/``-prefixed so it cannot
    collide with a project path of the same spelling. A ``@~/...`` token is
    left unfollowed, not reported as a problem, when ``sink.tilde_read`` is
    ``None`` (a valid construct, just unresolved).

    The starting file is depth 0. A file reached through
    :data:`MAX_IMPORT_DEPTH` hops (5) is still read, matching the observed
    "max depth 5" model, but its own imports are not: the chain caps at 5
    hops from the start file, not 5 files total. A cycle is a revisit of an
    ancestor in the *current* chain, not any file seen before; a second,
    non-cyclic path to an already-resolved file is deduplicated via
    ``sink.seen`` silently, not reported.

    Per-token resolution lives in :func:`_process_relative_import` and
    :func:`_process_tilde_import`; this function only decides whether to
    recurse into what they resolve, keeping its own branching (mccabe
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
                resolved = _process_tilde_import(raw, rel_path, sink)
                if resolved is not None:
                    assert sink.tilde_read is not None  # _process_tilde_import gates on this
                    key, data = resolved
                    _follow(key, data, depth + 1, (key,), sink.tilde_read, "user")
                continue
            resolved_relative = _process_relative_import(
                raw, rel_path, ancestors, active_read, active_layer, sink
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


def _add_and_walk(
    read_bytes: Callable[[str], bytes | None],
    rel_path: str,
    layer: str,
    sink: _ImportSink,
) -> None:
    """Add ``rel_path`` if it exists and is unseen, then follow its imports."""
    if rel_path in sink.seen:
        return
    data = read_bytes(rel_path)
    if data is None:
        return
    sink.seen.add(rel_path)
    sink.files.append(LoadedFile(layer, rel_path, len(data), f"{layer} file"))
    walk_claude_imports(read_bytes, rel_path, data, layer, sink)


def _resolve_claude_scoped(repo: Repo, target: str) -> list[LoadedFile]:
    """Scoped ``.claude/rules/*.md`` files, in both the working tree and at a rev.

    Filters to ``.md`` explicitly (matching ``all_copilot_instructions``'s
    own ``.instructions.md`` filter) rather than treating every listed name
    as a rule: ``Repo.list_dir`` returns every blob directly under the
    directory, working tree or rev alike, and a non-Markdown file there
    would otherwise be read and have its frontmatter parsed as if it were
    one.
    """
    files: list[LoadedFile] = []
    for rel_path in repo.list_dir(CLAUDE_RULES_DIR):
        if not rel_path.endswith(".md"):
            continue
        data = repo.read_bytes(rel_path)
        if data is None:
            continue
        text = data.decode("utf-8", errors="replace")
        patterns = parse_scope_patterns(text, "paths")
        if patterns is None:
            reason = "no paths: key (always loaded)"
        elif glob_matches(patterns, target):
            reason = "paths: matches target"
        else:
            continue
        files.append(LoadedFile("scoped", rel_path, len(data), reason))
    return files


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
    disk regardless of ``repo``'s rev because user config is not versioned.
    """
    tilde_read = (lambda rel: _home_read(Path.home(), rel)) if include_user else None
    sink = _ImportSink(tilde_read=tilde_read)

    for root_path in ("CLAUDE.md", ".claude/CLAUDE.md"):
        _add_and_walk(repo.read_bytes, root_path, "root", sink)

    for directory in directory_chain(base_dir):
        _add_and_walk(repo.read_bytes, f"{directory}/CLAUDE.md", "nested", sink)

    sink.files.extend(_resolve_claude_scoped(repo, target))

    if include_user:
        _add_user_root(sink)

    return sink.files, sink.problems


def _add_user_root(sink: _ImportSink) -> None:
    """Add ``~/.claude/CLAUDE.md`` (if present) and follow its imports.

    ``~/.claude/CLAUDE.md`` matches the loading model's own root layer row
    (``~/.claude/CLAUDE.md`` plus imports), not a bare ``~/CLAUDE.md``.
    ``key`` is passed as ``walk_claude_imports``'s ``start_rel`` (``~/``
    prefix included), so :func:`_process_relative_import` detects
    ``is_home`` immediately and resolves a relative import under
    ``~/.claude/``, not the home directory's own root.
    """
    home_bytes = _home_read(Path.home(), ".claude/CLAUDE.md")
    if home_bytes is None:
        return
    key = "~/.claude/CLAUDE.md"
    sink.seen.add(key)
    sink.files.append(LoadedFile("user", key, len(home_bytes), "user root file"))
    walk_claude_imports(lambda rel: _home_read(Path.home(), rel), key, home_bytes, "user", sink)
