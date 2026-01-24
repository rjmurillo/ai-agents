"""Memory Enhancement Layer for Serena + Forgetful.

This module provides citation verification and graph traversal capabilities
for Serena memories, inspired by GitHub Copilot's citation system.

Key Features:
- YAML frontmatter citations with file:line references
- Just-in-time verification of citation validity
- BFS/DFS graph traversal with cycle detection
- CLI interface for verification and graph operations
- Foundation for health reporting

Example:
    Verify a single memory:
        $ python -m memory_enhancement verify memory-001-feedback-retrieval

    Verify all memories:
        $ python -m memory_enhancement verify-all --dir .serena/memories

    Traverse memory graph:
        $ python -m memory_enhancement graph memory-001 --strategy bfs

    Find root memories:
        $ python -m memory_enhancement graph find-roots
"""

from .citations import VerificationResult, verify_all_memories, verify_citation, verify_memory
from .graph import MemoryGraph, TraversalNode, TraversalResult, TraversalStrategy
from .models import Citation, Link, LinkType, Memory

__all__ = [
    "Memory",
    "Citation",
    "Link",
    "LinkType",
    "VerificationResult",
    "verify_citation",
    "verify_memory",
    "verify_all_memories",
    "MemoryGraph",
    "TraversalStrategy",
    "TraversalNode",
    "TraversalResult",
]
