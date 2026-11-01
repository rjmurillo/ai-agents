"""Failure classifier: one shared definition of the tool-failure signals."""

from __future__ import annotations

from scripts.failure_classifier.classifier import (
    DENIAL_MARKERS,
    EDIT_TOOLS,
    FINGERPRINT_MAX_CHARS,
    TARGET_MAX_CHARS,
    FailureEvent,
    FailureSignals,
    canonical_input,
    canonicalize_input_text,
    classify,
    failure_fingerprint,
    fingerprint_tool,
    is_denial,
    normalize_target,
    normalize_tool,
)
from scripts.failure_classifier.transcript import events_from_records

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
    "fingerprint_tool",
    "is_denial",
    "normalize_target",
    "normalize_tool",
]
