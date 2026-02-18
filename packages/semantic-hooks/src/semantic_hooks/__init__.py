"""Semantic tension tracking hooks for Claude Code CLI."""

from semantic_hooks.core import HookContext, HookEvent, HookResult, SemanticNode
from semantic_hooks.guards import (
    StuckConfig,
    StuckDetectionGuard,
    StuckResult,
    check_stuck,
    extract_topic_signature,
    jaccard_similarity,
    reset_stuck_history,
)

# Lazy imports for heavy dependencies
def __getattr__(name: str):
    """Lazy import heavy modules to avoid numpy dependency for stuck detection."""
    if name == "SemanticGuard":
        from semantic_hooks.guards import SemanticGuard
        return SemanticGuard
    elif name == "SemanticMemory":
        from semantic_hooks.memory import SemanticMemory
        return SemanticMemory
    elif name == "SemanticRecorder":
        from semantic_hooks.recorder import SemanticRecorder
        return SemanticRecorder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__version__ = "0.1.0"
__all__ = [
    "HookContext",
    "HookEvent",
    "HookResult",
    "SemanticGuard",
    "SemanticMemory",
    "SemanticNode",
    "SemanticRecorder",
    # Stuck detection
    "StuckConfig",
    "StuckDetectionGuard",
    "StuckResult",
    "check_stuck",
    "extract_topic_signature",
    "jaccard_similarity",
    "reset_stuck_history",
]
