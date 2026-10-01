"""Data model for the typed dependency closure manifest.

ADR-101 ("What stays outside the loop") defines the protected set by function:
"any code or configuration whose behavior determines whether a gate's verdict is
computed, reported, or believed". It says that set must be computed, not
enumerated, as a typed closure with one resolver per edge kind, emitted as a
manifest and compared on every run. This module holds the manifest's shape.

Two rules from the ADR shape it:

  * "An edge that cannot be resolved fails closed rather than being omitted,
    since an omitted edge and a verified one are indistinguishable in the output
    otherwise." So an unresolved edge is a first-class entry, never a missing one.
  * `core.hooksPath` is "a recorded value the local gate reports rather than an
    edge the manifest resolves", and CODEOWNERS and the live ruleset are API state
    no import graph contains. So what a P1 run cannot observe is named in the
    manifest itself (`UNOBSERVABLE`) instead of being left out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1

EDGE_IMPORT = "module-import"
EDGE_CONFIG_COMMAND = "config-command"
EDGE_ACTION_INPUT = "action-input-file"
EDGE_WORKFLOW_REF = "workflow-reference"
EDGE_RUNTIME_CONFIG = "runtime-config"

# The five kinds a P1 runner can resolve. The sixth kind in the ADR's list, P2
# API state, is only partly observable, so it is named in UNOBSERVABLE below.
RESOLVED_KINDS = (
    EDGE_IMPORT,
    EDGE_CONFIG_COMMAND,
    EDGE_ACTION_INPUT,
    EDGE_WORKFLOW_REF,
    EDGE_RUNTIME_CONFIG,
)

UNOBSERVABLE: dict[str, str] = {
    "core.hooksPath": (
        "local Git configuration a P1 runner cannot observe; the local gate reports "
        "it as a recorded value"
    ),
    "p2-api-state": (
        "the live ruleset, its bypass actors and the CODEOWNERS a pull request is "
        "actually checked against are API state; only their repository-visible "
        "baselines are hashed here"
    ),
}


@dataclass(frozen=True, slots=True, order=True)
class Edge:
    """A resolved dependency: `source` reaches `target` by `kind`."""

    kind: str
    source: str
    target: str


@dataclass(frozen=True, slots=True, order=True)
class Unresolved:
    """An edge no resolver could resolve. Its presence fails the manifest closed."""

    kind: str
    source: str
    detail: str


@dataclass
class Manifest:
    """The computed closure: files by content hash, recorded values, and gaps."""

    entrypoints: set[str] = field(default_factory=set)
    files: dict[str, str] = field(default_factory=dict)
    edges: set[Edge] = field(default_factory=set)
    recorded: dict[str, str] = field(default_factory=dict)
    unresolved: set[Unresolved] = field(default_factory=set)

    def to_json(self) -> dict[str, Any]:
        """A deterministic document: same inputs, same bytes."""
        return {
            "schema": SCHEMA_VERSION,
            "resolved_kinds": list(RESOLVED_KINDS),
            "unobservable": dict(sorted(UNOBSERVABLE.items())),
            "entrypoints": sorted(self.entrypoints),
            "files": dict(sorted(self.files.items())),
            "edges": [[e.kind, e.source, e.target] for e in sorted(self.edges)],
            "recorded": dict(sorted(self.recorded.items())),
            "unresolved": [[u.kind, u.source, u.detail] for u in sorted(self.unresolved)],
        }


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[str]]:
    """Compare two manifest documents; every list is empty when nothing moved."""
    old_files, new_files = old.get("files", {}), new.get("files", {})
    old_rec, new_rec = old.get("recorded", {}), new.get("recorded", {})
    old_edges = {tuple(e) for e in old.get("edges", [])}
    new_edges = {tuple(e) for e in new.get("edges", [])}
    return {
        "files_added": sorted(set(new_files) - set(old_files)),
        "files_removed": sorted(set(old_files) - set(new_files)),
        "files_changed": sorted(
            p for p in new_files if p in old_files and new_files[p] != old_files[p]
        ),
        "recorded_changed": sorted(
            k for k in set(old_rec) | set(new_rec) if old_rec.get(k) != new_rec.get(k)
        ),
        "edges_added": sorted(" -> ".join(e) for e in new_edges - old_edges),
        "edges_removed": sorted(" -> ".join(e) for e in old_edges - new_edges),
    }
