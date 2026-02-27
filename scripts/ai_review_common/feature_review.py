"""Feature review parsing: recommendation, assignees, labels extraction."""

from __future__ import annotations

import re

VALID_RECOMMENDATIONS = frozenset(
    {
        "PROCEED",
        "DEFER",
        "REQUEST_EVIDENCE",
        "NEEDS_RESEARCH",
        "DECLINE",
    }
)

_RECOMMENDATION_PATTERN = re.compile(
    r"RECOMMENDATION:\s*(PROCEED|DEFER|REQUEST_EVIDENCE|NEEDS_RESEARCH|DECLINE)"
)

# Fallback rules when no explicit RECOMMENDATION: line is found.
# Order matters: DECLINE first (most conservative), then DEFER, then PROCEED.
# This prevents false positives like "PROCEED but DECLINE if X" from matching PROCEED.
_KEYWORD_FALLBACK_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bDECLINE\b"), "DECLINE"),
    (re.compile(r"\bDEFER\b"), "DEFER"),
    (re.compile(r"\bPROCEED\b"), "PROCEED"),
]

_ASSIGNEES_PATTERN = re.compile(r"\*{0,2}Assignees\*{0,2}:\s*(.+?)(?:\r?\n|$)", re.IGNORECASE)

_LABELS_PATTERN = re.compile(r"\*{0,2}Labels\*{0,2}:\s*(.+?)(?:\r?\n|$)", re.IGNORECASE)

_GITHUB_USERNAME_PATTERN = re.compile(r"@?([a-zA-Z0-9][-a-zA-Z0-9]*)")

_LABEL_BACKTICK_PATTERN = re.compile(r"`([^`]+)`")
_LABEL_PLAIN_PATTERN = re.compile(r"([a-zA-Z][-a-zA-Z0-9:]+)")

_NONE_VALUES = frozenset(
    {
        "none",
        "no one",
        "none suggested",
        "n/a",
        "no additional",
    }
)

_SKIP_WORDS = frozenset({"none", "suggested", "or", "and"})


def get_feature_review_recommendation(output: str) -> str:
    """Extract recommendation from feature review AI output.

    Parses the RECOMMENDATION line and returns one of:
    PROCEED, DEFER, REQUEST_EVIDENCE, NEEDS_RESEARCH, DECLINE.
    Returns UNKNOWN if no valid recommendation found.
    """
    if not output or not output.strip():
        return "UNKNOWN"

    match = _RECOMMENDATION_PATTERN.search(output)
    if match:
        return match.group(1)

    for pattern, recommendation in _KEYWORD_FALLBACK_RULES:
        if pattern.search(output):
            return recommendation

    return "UNKNOWN"


def get_feature_review_assignees(output: str) -> str:
    """Extract suggested assignees from feature review AI output.

    Returns comma-separated GitHub usernames or empty string.
    Skips "none suggested" type responses.
    """
    if not output or not output.strip():
        return ""

    match = _ASSIGNEES_PATTERN.search(output)
    if not match:
        return ""

    value = match.group(1).strip()
    value_lower = value.lower()

    for none_val in _NONE_VALUES:
        if value_lower.startswith(none_val):
            return ""

    usernames: list[str] = []
    for username_match in _GITHUB_USERNAME_PATTERN.finditer(value):
        username = username_match.group(1)
        if username.lower() not in _SKIP_WORDS:
            usernames.append(username)

    return ",".join(usernames)


def get_feature_review_labels(output: str) -> str:
    """Extract suggested labels from feature review AI output.

    Returns comma-separated labels or empty string.
    Handles both backtick-wrapped and plain labels.
    """
    if not output or not output.strip():
        return ""

    match = _LABELS_PATTERN.search(output)
    if not match:
        return ""

    value = match.group(1).strip()
    value_lower = value.lower()

    for none_val in _NONE_VALUES:
        if value_lower.startswith(none_val):
            return ""

    labels: list[str] = []

    for backtick_match in _LABEL_BACKTICK_PATTERN.finditer(value):
        label = backtick_match.group(1)
        if label and label.lower() not in _SKIP_WORDS:
            labels.append(label)

    # Also extract plain labels even if backtick labels were found
    for plain_match in _LABEL_PLAIN_PATTERN.finditer(value):
        label = plain_match.group(1)
        if label and label.lower() not in _SKIP_WORDS and label not in labels:
            labels.append(label)

    return ",".join(labels)
