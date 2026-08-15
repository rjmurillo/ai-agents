"""Checkpointed recursive discourse traversal for GitHub issues and PRs.

Provides BFS traversal of linked issues/PRs with persistent checkpointing.
On resume, enforces the invariant: len(visited) + len(pending) == discovered_count.
Detects parser version changes and refuses to resume with stale state.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# Reference parser
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(
    r"(?:^|\s)(?:"
    r"(?:https://github\.com/([^/]+/[^/]+)/(?:issues|pull)/(\d+))"
    r"|"
    r"#(\d+)"
    r")",
    re.MULTILINE,
)

PARSER_VERSION = "1"


class ReferenceParser(Protocol):
    """Protocol for extracting issue/PR references from text."""

    @property
    def version(self) -> str: ...

    def extract(self, text: str, repo: str) -> set[str]: ...


@dataclass
class DefaultParser:
    """Default regex-based reference parser."""

    version: str = PARSER_VERSION

    def extract(self, text: str, repo: str) -> set[str]:
        """Extract same-repo issue/PR references from text.

        Returns set of strings like 'owner/repo#123'. Cross-repo refs are excluded.
        """
        refs: set[str] = set()
        for match in _REF_PATTERN.finditer(text):
            if match.group(3):
                refs.add(f"{repo}#{match.group(3)}")
            elif match.group(1) and match.group(2):
                found_repo = match.group(1)
                number = match.group(2)
                if found_repo == repo:
                    refs.add(f"{repo}#{number}")
        return refs


# ---------------------------------------------------------------------------
# Checkpoint state
# ---------------------------------------------------------------------------


class InvariantError(Exception):
    """Raised when checkpoint invariant is violated on resume."""


class ParserVersionMismatchError(Exception):
    """Raised when checkpoint parser version differs from current parser."""


@dataclass
class Checkpoint:
    """Persistent traversal state."""

    schema_version: int = 1
    parser_version: str = PARSER_VERSION
    repo: str = ""
    visited: set[str] = field(default_factory=set)
    pending: list[str] = field(default_factory=list)
    discovered_count: int = 0
    edges: list[tuple[str, str]] = field(default_factory=list)
    exclusions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "repo": self.repo,
            "visited": sorted(self.visited),
            "pending": self.pending,
            "discovered_count": self.discovered_count,
            "edges": self.edges,
            "exclusions": self.exclusions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Checkpoint:
        return cls(
            schema_version=data.get("schema_version", 1),
            parser_version=data.get("parser_version", ""),
            repo=data.get("repo", ""),
            visited=set(data.get("visited", [])),
            pending=list(data.get("pending", [])),
            discovered_count=data.get("discovered_count", 0),
            edges=[tuple(e) for e in data.get("edges", [])],
            exclusions=dict(data.get("exclusions", {})),
        )

    def validate_invariant(self) -> None:
        """Enforce visited + queued == discovered."""
        actual = len(self.visited) + len(self.pending)
        if actual != self.discovered_count:
            raise InvariantError(
                f"Invariant violated: visited({len(self.visited)}) + "
                f"pending({len(self.pending)}) = {actual} != "
                f"discovered({self.discovered_count})"
            )


def save_checkpoint(checkpoint: Checkpoint, path: Path) -> None:
    """Atomically write checkpoint to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mktemp(dir=path.parent, suffix=".tmp"))
    try:
        tmp.write_text(
            json.dumps(checkpoint.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_checkpoint(path: Path, parser: ReferenceParser) -> Checkpoint:
    """Load checkpoint and validate invariant and parser version."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cp = Checkpoint.from_dict(data)

    if cp.parser_version != parser.version:
        raise ParserVersionMismatchError(
            f"Checkpoint parser version '{cp.parser_version}' != "
            f"current parser version '{parser.version}'"
        )

    cp.validate_invariant()
    return cp


# ---------------------------------------------------------------------------
# Fetcher protocol
# ---------------------------------------------------------------------------


class ItemFetcher(Protocol):
    """Protocol for fetching issue/PR body text."""

    def fetch_body(self, ref: str) -> str | None:
        """Fetch the body text for a reference like 'owner/repo#123'.

        Returns None if the item is not accessible.
        """
        ...


# ---------------------------------------------------------------------------
# Traversal engine
# ---------------------------------------------------------------------------


@dataclass
class TraversalResult:
    """Final result of a completed traversal."""

    visited: set[str]
    edges: list[tuple[str, str]]
    exclusions: dict[str, str]
    discovered_count: int


def traverse(
    *,
    seeds: list[str],
    repo: str,
    fetcher: ItemFetcher,
    parser: ReferenceParser | None = None,
    checkpoint_path: Path | None = None,
    batch_size: int = 10,
    max_items: int = 1000,
) -> TraversalResult:
    """BFS traverse discourse links with persistent checkpointing.

    Args:
        seeds: Initial references to start from (e.g. ['owner/repo#1']).
        repo: Repository in 'owner/repo' format for same-repo filtering.
        fetcher: Protocol implementation for fetching item bodies.
        parser: Reference parser (defaults to DefaultParser).
        checkpoint_path: Path for checkpoint persistence (None disables).
        batch_size: Items to process between checkpoint writes.
        max_items: Safety cap on total discovered items.

    Returns:
        TraversalResult with all visited nodes and edges.

    Raises:
        InvariantError: If resumed checkpoint fails invariant check.
        ParserVersionMismatchError: If parser version changed since checkpoint.
    """
    if parser is None:
        parser = DefaultParser()

    # Resume from checkpoint if available
    cp: Checkpoint
    if checkpoint_path and checkpoint_path.exists():
        cp = load_checkpoint(checkpoint_path, parser)
    else:
        # Initialize fresh state
        pending = []
        visited: set[str] = set()
        for seed in seeds:
            if seed not in visited:
                pending.append(seed)
                visited.discard(seed)  # noqa: not in visited already
        cp = Checkpoint(
            parser_version=parser.version,
            repo=repo,
            visited=set(),
            pending=pending,
            discovered_count=len(pending),
            edges=[],
            exclusions={},
        )

    processed_in_batch = 0

    while cp.pending:
        if len(cp.visited) >= max_items:
            break

        ref = cp.pending.pop(0)
        cp.visited.add(ref)

        body = fetcher.fetch_body(ref)
        if body is None:
            cp.exclusions[ref] = "not_accessible"
        else:
            new_refs = parser.extract(body, repo)
            for new_ref in new_refs:
                if new_ref not in cp.visited and new_ref not in cp.pending:
                    if cp.discovered_count >= max_items:
                        cp.exclusions[new_ref] = "max_items_reached"
                        continue
                    cp.pending.append(new_ref)
                    cp.discovered_count += 1
                cp.edges.append((ref, new_ref))

        processed_in_batch += 1

        if checkpoint_path and processed_in_batch >= batch_size:
            cp.validate_invariant()
            save_checkpoint(cp, checkpoint_path)
            processed_in_batch = 0

    # Final save
    if checkpoint_path:
        cp.validate_invariant()
        save_checkpoint(cp, checkpoint_path)

    return TraversalResult(
        visited=cp.visited,
        edges=cp.edges,
        exclusions=cp.exclusions,
        discovered_count=cp.discovered_count,
    )
