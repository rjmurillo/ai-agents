"""Memory Enhancement Layer for Serena + Forgetful.

Implements citation verification, graph traversal, and health reporting.
Per ADR-042: Python-first for AI/ML ecosystem alignment.

Usage:
    python -m memory_enhancement verify <memory-id-or-path>
    python -m memory_enhancement verify-all [--dir .serena/memories]
"""

from .models import Memory, Citation, Link, LinkType
from .citations import (
    verify_citation,
    verify_memory,
    verify_all_memories,
    VerificationResult,
    VerifyAllResult,
)

__all__ = [
    "Memory",
    "Citation",
    "Link",
    "LinkType",
    "verify_citation",
    "verify_memory",
    "verify_all_memories",
    "VerificationResult",
    "VerifyAllResult",
]
