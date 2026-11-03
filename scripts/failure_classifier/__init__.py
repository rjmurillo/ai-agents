"""Failure classifier: one shared definition of the tool-failure signals."""

from __future__ import annotations

from scripts.failure_classifier.classifier import (
    DENIAL_MARKERS,
    EDIT_TOOLS,
    FINGERPRINT_MAX_CHARS,
    FRICTION_TIER1_DEFAULT,
    FRICTION_WEIGHTS,
    SHELL_TOOLS,
    TARGET_MAX_CHARS,
    FailureEvent,
    FailureSignals,
    canonical_input,
    canonicalize_input_text,
    check_command,
    classify,
    failure_fingerprint,
    fingerprint_tool,
    friction_score,
    is_check_command,
    is_denial,
    normalize_target,
    normalize_tool,
)
from scripts.failure_classifier.transcript import events_from_records, stop_feedback_count

__all__ = [
    "DENIAL_MARKERS",
    "EDIT_TOOLS",
    "FINGERPRINT_MAX_CHARS",
    "FRICTION_TIER1_DEFAULT",
    "FRICTION_WEIGHTS",
    "SHELL_TOOLS",
    "TARGET_MAX_CHARS",
    "FailureEvent",
    "FailureSignals",
    "canonical_input",
    "canonicalize_input_text",
    "check_command",
    "classify",
    "events_from_records",
    "failure_fingerprint",
    "fingerprint_tool",
    "friction_score",
    "is_check_command",
    "is_denial",
    "normalize_target",
    "normalize_tool",
    "stop_feedback_count",
]
