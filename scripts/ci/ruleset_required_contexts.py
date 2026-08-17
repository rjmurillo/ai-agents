"""Pinned required-context contract for ruleset 11104075."""

from __future__ import annotations

REPOSITORY = "rjmurillo/ai-agents"
BRANCH = "main"
RULESET_ID = "11104075"

# Both the merge-group readiness gate and the scheduled detector import this
# contract. A second baseline would recreate the drift this check detects.
#
# Every context here is deterministic: a workflow either produces it or it does
# not, and the answer does not depend on a model. The six AI PR Quality Gate
# contexts (Analyst/Architect/DevOps/QA/Roadmap/Security Review) were removed
# with that workflow, and "Validate memory citations" went with them because
# memory-validation.yml is advisory rather than merge-blocking.
RETIRED_AI_REVIEW_CONTEXTS: frozenset[str] = frozenset(
    {
        "Analyst Review",
        "Architect Review",
        "DevOps Review",
        "QA Review",
        "Roadmap Review",
        "Security Review",
    }
)

# Unpinned, but not all for the same reason. The six above lost their producer
# when the gate was deleted. "Validate memory citations" still has one in
# memory-validation.yml; it is advisory and merely no longer blocks merge.
RETIRED_CONTEXTS: frozenset[str] = RETIRED_AI_REVIEW_CONTEXTS | frozenset(
    {"Validate memory citations"}
)

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
