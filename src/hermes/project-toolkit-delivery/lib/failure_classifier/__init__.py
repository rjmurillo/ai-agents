"""Failure classifier: the shared tool-failure signals for REQ-048's two consumers."""

from __future__ import annotations

from .classifier import (
    DENIAL_MARKERS,
    EDIT_TOOLS,
    FINGERPRINT_MAX_CHARS,
    TARGET_MAX_CHARS,
    FailureEvent,
    FailureSignals,
    classify,
    failure_fingerprint,
    is_denial,
    normalize_target,
    normalize_tool,
)
from .transcript import (
    canonical_input,
    canonicalize_input_text,
    events_from_records,
)

__all__ = [
    "DENIAL_MARKERS",
    "EDIT_TOOLS",
    "FINGERPRINT_MAX_CHARS",
    "TARGET_MAX_CHARS",
    "FailureEvent",
    "FailureSignals",
    "canonical_input",
    "canonicalize_input_text",
    "classify",
    "events_from_records",
    "failure_fingerprint",
    "is_denial",
    "normalize_target",
    "normalize_tool",
]
