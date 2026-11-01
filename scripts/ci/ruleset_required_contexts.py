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
        "Check whole-tree count ratchets (blocking)",
        "Run Python Tests",
        "Validate Generated Files",
        "Validate Path Normalization",
        "Validate PR",
        "Validate PR title",
        "Validate Plugin Version Bump",
    }
)

# Reasons a PR-triggered workflow is report-only. The branch ruleset does not wait
# on a report-only workflow, because none of its job names is in REQUIRED_CONTEXTS,
# so GitHub lets a pull request merge while it fails or stays pending. The local
# merge-readiness check (check_merge_readiness) is a separate policy and still
# rejects a failed non-required check that has no recorded disposition.
AI_QUOTA = (
    "model-driven: spends provider quota or waits on an agent-<cli> environment "
    "approval, so it must never gate a merge"
)
DETERMINISTIC = (
    "deterministic check: a job name is not pinned in the ruleset, so promoting "
    "it is a ruleset change, not a code change"
)
AUTOMATION = (
    "automation that labels, approves, or records a pull request; it returns no "
    "verdict about the change"
)

# Workflows that produce a context in REQUIRED_CONTEXTS. Every context above must
# come from one of these, and none of them may read a model credential.
REQUIRED_WORKFLOWS: frozenset[str] = frozenset(
    {
        "codeql-analysis.yml",
        "pr-validation.yml",
        "pytest.yml",
        "semantic-pr-title-check.yml",
        "validate-generated-agents.yml",
        "validate-paths.yml",
        "validate-plugin-version-bump.yml",
    }
)

# Every other workflow that runs on pull_request, pull_request_target, or
# merge_group, with the reason it is report-only.
# tests/ci/test_pr_workflow_classification.py fails when a PR-triggered workflow
# is in neither set, so adding one forces this decision.
REPORT_ONLY_WORKFLOWS: dict[str, str] = {
    "agent-drift-detection.yml": DETERMINISTIC,
    "agent-skill-discriminator-check.yml": DETERMINISTIC,
    "ai-spec-review.yml": AI_QUOTA,
    "ai-spec-validation.yml": DETERMINISTIC,
    "audit-hook-bypass.yml": DETERMINISTIC,
    "citation-verify.yml": DETERMINISTIC,
    "claude.yml": AI_QUOTA,
    "cli-smoke.yml": DETERMINISTIC,
    "dependabot-approve-and-auto-merge.yml": AUTOMATION,
    "dependency-review.yml": DETERMINISTIC,
    # Red by design when a pull request edits a file in the completion gate's
    # dispatch closure: the job reports every such edit (ADR-101, Application B).
    # It is the signal for a human to read that diff, not a defect, so it must
    # stay report-only.
    "enforcement-closure.yml": DETERMINISTIC,
    "hook-contract-check.yml": DETERMINISTIC,
    "installed-plugin-hook-guard.yml": DETERMINISTIC,
    "instruction-budget.yml": DETERMINISTIC,
    "investigation-claim-backstop.yml": DETERMINISTIC,
    "label-pr.yml": AUTOMATION,
    "memory-health.yml": DETERMINISTIC,
    "milestone-tracking.yml": AUTOMATION,
    "passive-context-budget.yml": DETERMINISTIC,
    "placeholder-identity-check.yml": DETERMINISTIC,
    "plugin-cli-smoke.yml": AI_QUOTA,
    "plugin-scanner.yml": DETERMINISTIC,
    "post-pr-retrospective.yml": AI_QUOTA,
    "skill-passive-compliance.yml": DETERMINISTIC,
    "skillbook-validation.yml": DETERMINISTIC,
    "slash-command-quality.yml": AI_QUOTA,
    "software-engineering-library-activation.yml": AI_QUOTA,
    "synthesis-panel-gate.yml": DETERMINISTIC,
    "test-codeql-integration.yml": DETERMINISTIC,
    "validate-adr-number-uniqueness.yml": DETERMINISTIC,
    "validate-artifact-retention.yml": DETERMINISTIC,
    "validate-planning-artifacts.yml": DETERMINISTIC,
    "validate-plugin-manifests.yml": DETERMINISTIC,
    "validate-rule-activation-coverage.yml": DETERMINISTIC,
    "validate-spec-id-uniqueness.yml": DETERMINISTIC,
    "validate-vendor-portability.yml": DETERMINISTIC,
    "yaml-lint.yml": DETERMINISTIC,
}

REFRESH_COMMAND = (
    f"gh api repos/{REPOSITORY}/rulesets/{RULESET_ID} \\\n"
    '  --jq \'.rules[] | select(.type=="required_status_checks") '
    "| .parameters.required_status_checks[].context' \\\n"
    "  | sort"
)
