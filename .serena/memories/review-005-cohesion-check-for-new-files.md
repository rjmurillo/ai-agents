# Review: Cohesion Check For New Files

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