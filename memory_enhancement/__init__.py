"""Memory Enhancement Layer for Serena + Forgetful.

This package provides citation validation and graph traversal capabilities
for Serena memories without replacing the existing memory system.

Key components:
- models: Data structures for memories, citations, and typed links
- graph: BFS/DFS traversal and relationship navigation
"""

from .graph import (
    find_blocking_dependencies,
    find_related_memories,
    find_root_memories,
    find_superseded_chain,
    traverse_graph,
)
from .models import Citation, GraphEdge, GraphResult, Link, LinkType, Memory

__version__ = "0.1.0"

__all__ = [
    # Models
    "Memory",
    "Citation",
    "Link",
    "LinkType",
    "GraphEdge",
    "GraphResult",
    # Graph operations
    "traverse_graph",
    "find_related_memories",
    "find_root_memories",
    "find_superseded_chain",
    "find_blocking_dependencies",
]
