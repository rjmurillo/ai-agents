"""Memory Enhancement Layer for Serena + Forgetful.

This module provides citation verification and graph traversal capabilities
for Serena memories, inspired by GitHub Copilot's citation system.

Key Features:
- YAML frontmatter citations with file:line references
- Just-in-time verification of citation validity
- CLI interface for verification and reporting
- Foundation for graph traversal and health reporting

Example:
    Verify a single memory:
        $ python -m memory_enhancement verify memory-001-feedback-retrieval

    Verify all memories:
        $ python -m memory_enhancement verify-all --dir .serena/memories
"""

from .citations import VerificationResult, verify_all_memories, verify_citation, verify_memory
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
]
