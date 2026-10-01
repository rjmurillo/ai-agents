"""Adapter over ``check_capability_graph`` for the instruction-byte report (issue #5400).

``check_capability_graph`` imports its sibling ``instruction_budget_globs`` by
bare name so it can run as a script. Every other module in this report imports
the same sibling through the ``scripts.validation.`` package prefix. The per-file
mypy gate runs with ``MYPYPATH=scripts/validation`` and rejects a file it finds
under two names, so this adapter is the only place the bare-name module loads,
and it loads it with ``importlib`` where mypy does not follow it.

What it reads from the gate, on this checkout (issue #5396, ADR-110):

* ``PROJECTION_GLOBS``: every generated mirror root and glob;
* ``NAME_RE``: the artifact-name pattern, ``^[a-z0-9-]{1,64}$``;
* ``collect_nodes`` and ``build_owner_index``: the capability nodes and the
  capability-name to canonical-owner index.
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

__all__ = ["Capability", "Graph", "load_graph", "name_pattern", "projection_globs"]

_VALIDATION_DIR = str(Path(__file__).resolve().parent)


@dataclass(frozen=True)
class Capability:
    """One artifact's ``metadata.capability`` declaration, reduced to what the report reads."""

    path: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class Graph:
    """Capability nodes by repository path, canonical owners by capability name."""

    nodes: dict[str, Capability]
    owners: dict[str, Capability]
    defects: tuple[str, ...]


def _gate() -> ModuleType:
    if _VALIDATION_DIR not in sys.path:
        sys.path.insert(0, _VALIDATION_DIR)
    return importlib.import_module("check_capability_graph")


def projection_globs() -> tuple[tuple[str, str], ...]:
    """Return the gate's ``(directory, glob)`` pairs for generated mirrors."""
    globs: tuple[tuple[str, str], ...] = _gate().PROJECTION_GLOBS
    return globs


def name_pattern() -> re.Pattern[str]:
    """Return the gate's artifact-name pattern."""
    pattern: re.Pattern[str] = _gate().NAME_RE
    return pattern


def load_graph(repo_root: Path) -> Graph:
    """Read the capability graph once. A tree the gate cannot read raises ``ValueError``."""
    gate = _gate()
    try:
        nodes, defects = gate.collect_nodes(repo_root)
    except gate.TreeError as exc:
        raise ValueError(f"capability graph unreadable: {exc}") from exc
    owner_index, owner_findings = gate.build_owner_index(nodes)
    by_path = {n.path: Capability(n.path, tuple(n.depends_on)) for n in nodes}
    owners = {name: by_path[node.path] for name, node in owner_index.items()}
    return Graph(by_path, owners, tuple(sorted([*defects, *owner_findings])))
