"""Memory Core: shared modules for the memory skill system.

Provides schema validation, memory routing, and reflexion memory capabilities.
Migrated from PowerShell modules per issue #1061 (ADR-042).
"""

from __future__ import annotations

from .memory_router import (
    MemoryResult,
    get_content_hash,
    get_memory_router_status,
    invoke_serena_search,
    reset_caches,
    search_memory,
)
from .reflexion_memory import (
    get_decision_sequence,
    get_episode,
    get_episodes,
    get_reflexion_memory_status,
    new_episode,
)
from .schema_validation import (
    ValidationResult,
    WriteResult,
    clear_schema_cache,
    get_schema_path,
    test_schema_valid,
    write_validated_json,
)
from .url_validation import (
    ALLOWED_URL_SCHEMES,
    validate_http_url,
)

__all__ = [
    # URL validation
    "ALLOWED_URL_SCHEMES",
    "validate_http_url",
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
    "invoke_serena_search",
    "reset_caches",
    "search_memory",
    # Reflexion memory
    "get_decision_sequence",
    "get_episode",
    "get_episodes",
    "get_reflexion_memory_status",
    "new_episode",
]
