"""Regenerate scripts/validation/effective_context_ceilings.py (issue #4880).

Coordinator finding (post-rebase review): every one of ``CEILINGS_BYTES``'s
10 entries and ``PATH_LOCAL_DIRECTORY_CEILINGS``'s 124 entries was a
hand-typed byte count equal to some earlier measurement. A one-byte edit to
``src/AGENTS.md`` cascades into every ``src/*`` entry, and nothing
regenerated them: a maintainer had to re-run the CLI once per (target,
harness) pair and hand-copy each new count.

``--write-ceilings`` on ``python -m scripts.validation.effective_context``
calls :func:`write_ceilings_module` here instead. It re-measures every
frozen target (``FROZEN_TARGETS``) and every git-tracked instructed
directory (``discover_nested_directories``) for both harnesses, then
rewrites ``effective_context_ceilings.py`` from that measurement: sorted
keys, one rendering function, so two runs against the same repository state
produce byte-identical output. A maintainer reviews the diff like any other
generated file and commits it; the ratchet's own breach messages
(``effective_context.py``'s ``_format_breach`` and
``_format_missing_ceiling``) name this flag as the command that accepts a
reviewed change.

Kept out of ``effective_context_ceilings.py`` itself (that module documents
itself as pure data, read by name so a monkeypatched
``effective_context.CEILINGS_BYTES`` still reaches the same functions) and
out of ``effective_context.py`` (already near the taste-lints file-size
warning band). This module only writes; it never reads the ceiling
constants it produces, so it carries none of the monkeypatch constraint
``effective_context_ceilings.py`` documents.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation.effective_context_ceilings import (
    CEILING_LABEL,
    FROZEN_TARGETS,
    HARNESSES,
)
from scripts.validation.effective_context_resolvers import (
    discover_nested_directories,
    resolve_effective_context,
)

CeilingMap = dict[tuple[str, str], int]

# The one shape `check_agents_write_targets.py`'s `_find_agents_join` misreads
# as a `.agents/<name>` path join: a 2-element tuple literal whose first
# element is the literal string `.agents` immediately followed by another
# string constant (verified this session, `check_agents_write_targets.py`
# lines 203-213). `PATH_LOCAL_DIRECTORY_CEILINGS`'s `(".agents", "claude")`
# and `(".agents", "copilot")` keys are that exact shape; every other key in
# either map either is not `.agents` or is a longer path under it
# (`.agents/archive/...`), so it does not match. Suppressed here the same
# way the hand-written file already was, so a fresh `--write-ceilings` run
# does not reintroduce the taste-lints false positive it was previously
# fixed for.
_AGENTS_JOIN_FALSE_POSITIVE_DIRECTORY = ".agents"
_AGENTS_JOIN_SUPPRESSION_COMMENT = (
    "  # agents-write-target: historical -- dict key, not a path join"
)


def measure_ceilings(repo_root: Path) -> tuple[CeilingMap, CeilingMap]:
    """Re-measure every frozen target and every discovered directory.

    Returns ``(frozen, per_directory)``, each ``(target_or_directory,
    harness) -> path_local_bytes``: the exact shape ``CEILINGS_BYTES`` and
    ``PATH_LOCAL_DIRECTORY_CEILINGS`` already hold, so
    :func:`render_ceilings_module` can render either without a conversion
    step. Raises :class:`GitUnavailableError` when ``discover_nested_directories``
    cannot enumerate the repository's tracked files (a broken or missing
    ``git``), matching every other ratchet check in this package.
    """
    frozen: CeilingMap = {}
    for target in FROZEN_TARGETS:
        for harness in HARNESSES:
            result = resolve_effective_context(repo_root, target, harness)
            frozen[(target, harness)] = result.path_local_bytes
    directories, _excluded = discover_nested_directories(repo_root)
    per_directory: CeilingMap = {}
    for directory in directories:
        for harness in HARNESSES:
            result = resolve_effective_context(repo_root, directory, harness)
            per_directory[(directory, harness)] = result.path_local_bytes
    return frozen, per_directory


def _dquote(value: str) -> str:
    """Render ``value`` as a double-quoted Python string literal.

    Every path and harness name this module writes is a plain repository
    path or ``"claude"``/``"copilot"``, none containing a quote or
    backslash; the escaping below only guards against a future value that
    does, rather than assuming today's inputs stay that way forever.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_str_tuple(name: str, values: tuple[str, ...]) -> str:
    """Render ``name: tuple[str, ...] = (...)``, one line if it is short."""
    single_line = f"{name}: tuple[str, ...] = ({', '.join(_dquote(v) for v in values)})"
    if len(values) <= 2 and len(single_line) <= 88:
        return single_line
    items = "\n".join(f"    {_dquote(value)}," for value in values)
    return f"{name}: tuple[str, ...] = (\n{items}\n)"


def _format_ceiling_map(name: str, ceilings: CeilingMap) -> str:
    """Render one ceiling dict literal, keys sorted, `.agents` suppressed."""
    lines = [f"{name}: dict[tuple[str, str], int] = {{"]
    for (key, harness), value in sorted(ceilings.items()):
        entry = f"    ({_dquote(key)}, {_dquote(harness)}): {value},"
        if key == _AGENTS_JOIN_FALSE_POSITIVE_DIRECTORY:
            entry += _AGENTS_JOIN_SUPPRESSION_COMMENT
        lines.append(entry)
    lines.append("}")
    return "\n".join(lines)


def render_ceilings_module(frozen: CeilingMap, per_directory: CeilingMap) -> str:
    """Render ``effective_context_ceilings.py``'s full source, deterministically.

    Same output for the same measurement every time: sorted keys, no
    hand-typed duplicate of ``FROZEN_TARGETS``/``HARNESSES``/``CEILING_LABEL``
    (each is printed back from the value already imported from
    ``effective_context_ceilings``, so this module cannot drift from what
    that module declares for the parts ``--write-ceilings`` never touches).
    """
    lines = [
        _MODULE_DOCSTRING,
        "",
        "from __future__ import annotations",
        "",
        '# Frozen targets from SPEC-4880-path-local-effective-context.md, "Frozen',
        '# targets" table. --write-ceilings never edits this tuple: adding or',
        "# removing a frozen target is a spec decision, not a measurement.",
        _format_str_tuple("FROZEN_TARGETS", FROZEN_TARGETS),
        "",
        _format_str_tuple("HARNESSES", HARNESSES),
        "",
        "CEILING_LABEL: str = (",
        *(f"    {_dquote(chunk)}" for chunk in _split_label(CEILING_LABEL)),
        ")",
        "",
        "# Re-measured by --write-ceilings for every frozen target above, both",
        "# harnesses. Issue #4880 AC7: PATH_LOCAL_DIRECTORY_CEILINGS below covers",
        "# every OTHER git-tracked directory with a nested CLAUDE.md/AGENTS.md, so",
        "# growth outside the five frozen targets is caught too. See",
        "# CEILING_LABEL above: local, measured, no vendor limit implied.",
        _format_ceiling_map("CEILINGS_BYTES", frozen),
        "",
        _format_ceiling_map("PATH_LOCAL_DIRECTORY_CEILINGS", per_directory),
        "",
    ]
    return "\n".join(lines)


_MODULE_DOCSTRING = (
    '"""Ratchet ceilings for path-local effective context (issue #4880).\n'
    "\n"
    "`uv run python -m scripts.validation.effective_context --write-ceilings`\n"
    "re-measures CEILINGS_BYTES and PATH_LOCAL_DIRECTORY_CEILINGS and rewrites\n"
    "this module. Review that diff like any code change. FROZEN_TARGETS,\n"
    "HARNESSES, and CEILING_LABEL come from the spec and are carried over.\n"
    "effective_context.py imports these names, so a test that monkeypatches\n"
    "them there reaches the functions that read them.\n"
    '"""'
)


def _split_label(label: str, width: int = 66) -> list[str]:
    """Wrap ``label`` into fixed-width word-boundary chunks, each a string literal.

    Mirrors the hand-wrapped style ``CEILING_LABEL`` already used (several
    short quoted lines joined by adjacent-string-literal concatenation), so
    a regenerated file reads the same way a hand-edited one did.
    """
    words = label.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            chunks.append(current + " ")
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def write_ceilings_module(repo_root: Path, ceilings_path: Path) -> str:
    """Measure, render, and write ``ceilings_path``. Returns the text written.

    Raises :class:`GitUnavailableError` when ``discover_nested_directories``
    cannot enumerate tracked files, the same ADR-035 exit-code-3 case every
    other ratchet check in this package raises.
    """
    frozen, per_directory = measure_ceilings(repo_root)
    text = render_ceilings_module(frozen, per_directory)
    ceilings_path.parent.mkdir(parents=True, exist_ok=True)
    ceilings_path.write_text(text, encoding="utf-8")
    return text
