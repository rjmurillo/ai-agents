"""Memory Core: shared modules for the memory skill system.

Provides schema validation, memory routing, and reflexion memory capabilities.
Migrated from PowerShell modules per issue #1061 (ADR-042).
"""

from __future__ import annotations

from .memory_router import (  # noqa: F401
    MemoryResult,
    get_content_hash,
    get_memory_router_status,
    invoke_forgetful_search,
    invoke_serena_search,
    merge_memory_results,
    reset_caches,
    search_memory,
    test_forgetful_available,
)
from .reflexion_memory import (  # noqa: F401
    add_causal_edge,
    add_causal_node,
    add_pattern,
    get_anti_patterns,
    get_causal_path,
    get_decision_sequence,
    get_episode,
    get_episodes,
    get_patterns,
    get_reflexion_memory_status,
    new_episode,
)
from .schema_validation import (  # noqa: F401
    ValidationResult,
    WriteResult,
    clear_schema_cache,
    get_schema_path,
    test_schema_valid,
    write_validated_json,
)

__all__ = [
    # Schema validation
    "ValidationResult",
    "WriteResult",
    "clear_schema_cache",
    "get_schema_path",
    "test_schema_valid",
    "write_validated_json",
    # Memory router
    "MemoryResult",
    "get_content_hash",
    "get_memory_router_status",
    "invoke_forgetful_search",
    "invoke_serena_search",
    "merge_memory_results",
    "reset_caches",
    "search_memory",
    "test_forgetful_available",
    # Reflexion memory
    "add_causal_edge",
    "add_causal_node",
    "add_pattern",
    "get_anti_patterns",
    "get_causal_path",
    "get_decision_sequence",
    "get_episode",
    "get_episodes",
    "get_patterns",
    "get_reflexion_memory_status",
    "new_episode",
]
