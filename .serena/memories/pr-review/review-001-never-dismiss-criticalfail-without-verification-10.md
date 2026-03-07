# Review: Never Dismiss Criticalfail Without Verification 10

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