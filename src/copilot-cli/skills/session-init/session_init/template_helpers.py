"""Template processing helpers for session log generation.

Provides functions to populate session log templates with actual values
and extract descriptive keywords from objectives.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from .common_types import ApplicationFailedError

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "should", "could", "may", "might",
    "can", "this", "that", "these", "those", "i", "you", "he", "she", "it",
    "we", "they", "what", "which", "who", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "s", "t", "just", "now", "before", "after", "new",
})

_REQUIRED_PLACEHOLDERS = [
    (r"\bNN\b", "NN (session number)"),
    (r"YYYY-MM-DD", "YYYY-MM-DD (date)"),
    (r"\[branch name\]", "[branch name]"),
    (r"\[SHA\]", "[SHA]"),
    (r"\[What this session aims to accomplish\]", "[What this session aims to accomplish]"),
    (r"\[clean/dirty\]", "[clean/dirty]"),
]


def get_descriptive_keywords(objective: str) -> str:
    """Extract descriptive keywords from session objective for filename.

    Returns up to 5 most relevant keywords in kebab-case,
    or empty string if no keywords can be extracted.
    """
    if not objective or not objective.strip():
        return ""

    words = re.sub(r"[^\w\s-]", "", objective).lower().split()

    keywords = [
        w for w in words
        if len(w) > 2 and w not in _STOP_WORDS
    ][:5]

    result = "-".join(keywords)
    result = re.sub(r"^-+", "", result)
    result = re.sub(r"-+$", "", result)
    result = re.sub(r"-{2,}", "-", result)
    return result


def new_populated_session_log(
    template: str,
    git_info: dict[str, str],
    user_input: dict[str, object],
    *,
    skip_validation: bool = False,
) -> str:
    """Replace template placeholders with actual values.

    Args:
        template: Session log template string with placeholders.
        git_info: Dict with keys branch, commit, status.
        user_input: Dict with keys session_number (int), objective (str).
        skip_validation: If True, warn instead of raising on missing placeholders.

    Returns:
        Populated session log string.

    Raises:
        ValueError: Template missing required placeholders (when skip_validation is False).
        ApplicationFailedError: Unexpected errors during processing.
    """
    try:
        missing = [
            name for pattern, name in _REQUIRED_PLACEHOLDERS
            if not re.search(pattern, template)
        ]

        if missing:
            detail = ", ".join(missing)
            if skip_validation:
                import sys
                print(
                    f"WARNING: Template missing required placeholders: {detail}. "
                    "Proceeding due to skip_validation.",
                    file=sys.stderr,
                )
            else:
                raise ValueError(
                    f"Template missing required placeholders: {detail}\n\n"
                    "This indicates a version mismatch with SESSION-PROTOCOL.md. "
                    "Session log cannot be created."
                )

        current_date = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        populated = template
        populated = re.sub(r"\bNN\b", str(user_input["session_number"]), populated)
        populated = populated.replace("YYYY-MM-DD", current_date)
        populated = populated.replace("[branch name]", git_info["branch"])
        populated = populated.replace("[SHA]", git_info["commit"])
        populated = populated.replace(
            "[What this session aims to accomplish]",
            str(user_input["objective"]),
        )
        populated = populated.replace("[clean/dirty]", git_info["status"])

        unreplaced = []
        if re.search(r"\bNN\b", populated):
            unreplaced.append("NN")
        markers = [
            "[branch name]", "[SHA]",
            "[What this session aims to accomplish]",
            "[clean/dirty]",
        ]
        for marker in markers:
            if marker in populated:
                unreplaced.append(marker)

        if unreplaced:
            detail = ", ".join(unreplaced)
            if skip_validation:
                import sys
                print(
                    f"WARNING: Placeholders not replaced: {detail}",
                    file=sys.stderr,
                )
            else:
                raise ValueError(
                    f"Placeholders were not replaced: {detail}\n\n"
                    "This indicates a validation failure."
                )

        return populated

    except ValueError:
        raise
    except Exception as exc:
        msg = (
            f"UNEXPECTED ERROR in new_populated_session_log\n"
            f"Exception Type: {type(exc).__name__}\n"
            f"Message: {exc}\n\n"
            f"This is a bug. Please report this error with the above details."
        )
        raise ApplicationFailedError(msg) from exc
