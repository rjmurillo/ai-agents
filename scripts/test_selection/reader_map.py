"""Narrow a test-input change to the tests that read it (issue #5377).

A changed Markdown, JSON, or text file is a `TEST_INPUT` in the path policy.
Before this module that verdict ran the whole suite even when one test read the
file. Here a changed input maps to the modules that name it in a string constant,
and to every module that walks a directory tree, because a walker can read any
path and no literal bounds it. The reverse import closure of those modules,
filtered to pytest files, is the selection.

The rule fails closed on both sides. A path outside the content suffixes (a
lock file, `pyproject.toml`, `lefthook.yml`, a workflow) is not narrowed at all,
and an empty result is promoted to a full run by the caller.
"""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from scripts.test_selection import import_graph

if TYPE_CHECKING:
    from collections.abc import Iterable

# Only content files are narrowed. Every other test input (dependency locks,
# pytest configuration, workflows, hook config, the policy file itself) keeps
# running the full suite.
NARROWABLE_SUFFIXES = frozenset({".md", ".json", ".txt"})

# Content-suffix files that still change how the suite installs or collects.
_INFRASTRUCTURE_NAMES = (
    "requirements*.txt",
    "constraints*.txt",
    "package.json",
    "package-lock.json",
)


def is_narrowable(rel: str) -> bool:
    """True when ``rel`` is a content file whose readers can be traced."""
    path = PurePosixPath(rel)
    if path.suffix not in NARROWABLE_SUFFIXES:
        return False
    return not any(fnmatch.fnmatch(path.name, name) for name in _INFRASTRUCTURE_NAMES)


def _normalize(literal: str) -> str:
    value = literal.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.rstrip("/")


def candidate_literals(rel: str) -> set[str]:
    """Every string a test could write that names ``rel``.

    The path itself, each trailing run of components (``b/c.md`` and ``c.md``
    for ``a/b/c.md``), and each contiguous run of directory components
    (``docs`` or ``docs/sub`` for ``docs/sub/x.md``).
    """
    parts = rel.split("/")
    candidates = {"/".join(parts[start:]) for start in range(len(parts))}
    directories = parts[:-1]
    for start in range(len(directories)):
        for stop in range(start + 1, len(directories) + 1):
            candidates.add("/".join(directories[start:stop]))
    return {candidate for candidate in candidates if len(candidate) > 1}


def literal_readers(rels: Iterable[str], graph_data: import_graph.ImportGraphData) -> set[str]:
    """Modules with a string constant that names any path in ``rels``."""
    index: dict[str, set[str]] = {}
    for module, literals in graph_data.string_literals.items():
        for literal in literals:
            index.setdefault(_normalize(literal), set()).add(module)
    readers: set[str] = set()
    for rel in rels:
        for candidate in candidate_literals(rel):
            readers.update(index.get(candidate, ()))
    return readers


def reader_tests(rels: Iterable[str], graph_data: import_graph.ImportGraphData) -> set[str]:
    """Test files that transitively import a reader of ``rels`` or any walker."""
    readers = literal_readers(rels, graph_data) | set(graph_data.tree_walkers)
    reverse = import_graph.reverse_graph(graph_data.graph)
    return import_graph.affected_closure(readers, reverse)
