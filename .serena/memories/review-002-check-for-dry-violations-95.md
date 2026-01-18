# Review: Check For Dry Violations 95

## Skill-Review-002: Check for DRY Violations (95%)

**Statement**: Before approving new code, search for existing helpers that provide the same functionality.

**Context**: PR review of scripts that add new functions.

**Trigger**: New PR adds utility functions or helper methods.

**Pattern**:

1. List new functions added in PR
2. For each function, search codebase for similar functionality
3. Check existing modules (e.g., GitHubHelpers.psm1, AIReviewCommon.psm1)
4. Flag any duplication as requiring resolution

**Evidence**: PR #147 duplicated Write-ErrorAndExit and API helper patterns that exist in GitHubHelpers.psm1.