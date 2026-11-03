"""Failure classifier: one shared definition of the tool-failure signals."""

from __future__ import annotations

from .classifier import (
    DENIAL_MARKERS,
    EDIT_TOOLS,
    FINGERPRINT_MAX_CHARS,
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
    is_check_command,
    is_denial,
    normalize_target,
    normalize_tool,
)
from .transcript import events_from_records

__all__ = [
    "DENIAL_MARKERS",
    "EDIT_TOOLS",
    "FINGERPRINT_MAX_CHARS",
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
    "is_check_command",
    "is_denial",
    "normalize_target",
    "normalize_tool",
]
