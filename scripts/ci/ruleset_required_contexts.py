"""Pinned required-context contract for ruleset 11104075."""

from __future__ import annotations

REPOSITORY = "rjmurillo/ai-agents"
BRANCH = "main"
RULESET_ID = "11104075"

# Both the merge-group readiness gate and the scheduled detector import this
# contract. A second baseline would recreate the drift this check detects.
REQUIRED_CONTEXTS: frozenset[str] = frozenset(
    {
        "Analyze (actions)",
        "Analyze (python)",
        "Run Python Tests",
        "Validate Generated Files",
        "Validate Path Normalization",
        "Validate PR",
        "Validate PR title",
        "Validate Plugin Version Bump",
        "Validate Spec Coverage",
    }
)

REFRESH_COMMAND = (
    f"gh api repos/{REPOSITORY}/rulesets/{RULESET_ID} \\\n"
    "  --jq '.rules[] | select(.type==\"required_status_checks\") "
    "| .parameters.required_status_checks[].context' \\\n"
    "  | sort"
)
