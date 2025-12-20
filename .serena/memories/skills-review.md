# Review Skills

Skills for conducting high-quality code and PR reviews.

## Skill-Review-001: Never Dismiss CRITICAL_FAIL Without Verification (100%)

**Statement**: When any agent returns CRITICAL_FAIL, personally verify the claim before dismissing it.

**Context**: PR review with multiple AI agents providing verdicts.

**Trigger**: Agent returns CRITICAL_FAIL while others return PASS.

**Pattern**:

1. Read the agent's specific findings
2. Verify the claim by reading actual code
3. If claim is valid, require fixes before approval
4. If claim is invalid, document why it's a false positive

**Evidence**: PR #147 in rjmurillo/ai-agents (2025-12-20): QA correctly identified missing functional tests, but reviewer dismissed based on majority vote.

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

## Skill-Review-003: Pattern-Based Tests Are Insufficient (98%)

**Statement**: Tests that only use regex pattern matching on code structure do not verify behavior. Functional tests with mocks are required.

**Context**: PR review of PowerShell scripts with Pester tests.

**Trigger**: Test file uses `Should -Match` on script content.

**Pattern**:

1. Check if tests actually execute functions
2. Verify Mock blocks exist for external dependencies
3. Confirm edge cases (null input, empty arrays, errors) are tested
4. If tests only pattern-match, flag CRITICAL_FAIL

**Evidence**: PR #147 had 60 "tests" that only verified code patterns, not behavior.

## Skill-Review-004: Read Actual Code Not Just Summaries (92%)

**Statement**: Agent summaries may miss issues. Always read key files in full before approval.

**Context**: PR review with AI agent analysis.

**Trigger**: Reviewing PR for final approval decision.

**Pattern**:

1. Read agent findings as input, not final verdict
2. Open and read the actual changed files
3. Look for issues agents might have missed (DRY, cohesion, bugs)
4. Make approval decision based on personal assessment

**Evidence**: PR #147 - Agent summaries said "PASS" but actual code had functional bugs.

## Skill-Review-005: Cohesion Check for New Files (88%)

**Statement**: New files should be in the right location. Question unnecessary directory nesting.

**Context**: PR review that adds new directories or files.

**Trigger**: New directory structure added in PR.

**Pattern**:

1. Ask: Does this directory nesting serve a purpose?
2. Ask: Could this file live one level up?
3. Ask: Is there an existing directory where this belongs?
4. Flag unnecessary complexity

**Evidence**: PR #147 created scripts/copilot/ subdirectory without clear justification.

## Skill-Review-007: Merge-Verdicts is Correct - Judgment is the Failure (100%)

**Statement**: The AI Quality Gate Merge-Verdicts function correctly propagates CRITICAL_FAIL. When CRITICAL_FAIL verdicts are "ignored", the failure is in human/agent judgment, not the code.

**Context**: Debugging why CRITICAL_FAIL didn't block a PR.

**Trigger**: Belief that Merge-Verdicts "averages out" or "majority votes" verdicts.

**Pattern**:

1. DO NOT blame the code - Merge-Verdicts returns CRITICAL_FAIL immediately if ANY verdict is CRITICAL_FAIL
2. The failure is in the review process BEFORE Merge-Verdicts is called
3. Check: Did the reviewer correctly interpret agent findings?
4. Check: Did the reviewer dismiss a valid CRITICAL_FAIL finding?

**Evidence**: PR #147 - AIReviewCommon.psm1:302-306 shows immediate return on CRITICAL_FAIL. The failure was reviewer judgment, not code.

## Skill-Review-005: Cohesion Check for New Files

**Statement**: New files should be in the right location. Question unnecessary directory nesting.

**Context**: PR review that adds new directories or files.

**Trigger**: New directory structure added in PR.

**Pattern**:

1. Ask: Does this directory nesting serve a purpose?
2. Ask: Could this file live one level up?
3. Ask: Is there an existing directory where this belongs?
4. Flag unnecessary complexity

**Evidence**: PR #147 created scripts/copilot/ subdirectory without clear justification.

## Skill-Review-006: @mention Bot Authors on Review Feedback (100%)

**Statement**: When posting review comments on bot-authored PRs, always @mention the bot so it receives notification.

**Context**: PR review of bot-authored changes (copilot-swe-agent, dependabot, etc.).

**Trigger**: Posting review comments or change requests on bot PR.

**Pattern**:

1. Identify PR author (check if bot)
2. Include @mention in review comment or follow-up
3. **IMPORTANT**: For GitHub Copilot PRs (author shows as `copilot-swe-agent`): use `@copilot` NOT `@copilot-swe-agent`
4. For dependabot: `@dependabot`

**Evidence**: PR #147 - Initial change request posted without @mention; Copilot unaware of feedback until explicitly mentioned.

**Nuance**: The PR author displays as `copilot-swe-agent` but the correct @mention is `@copilot`. This is confusing but confirmed behavior.
