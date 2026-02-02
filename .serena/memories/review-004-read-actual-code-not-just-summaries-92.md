# Review: Read Actual Code Not Just Summaries 92

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