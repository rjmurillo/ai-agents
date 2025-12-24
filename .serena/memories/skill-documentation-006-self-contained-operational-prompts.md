# Skill-Documentation-006: Self-Contained Operational Prompts

**Statement**: Include all resource constraints, failure modes, shared resource context, and dynamic adjustment rules for autonomous agents.

**Context**: Prompts intended for standalone Claude instances or autonomous agents.

**Evidence**: PR #301 - Rate limit guidance missing from autonomous-pr-monitor.md.

**Atomicity**: 88% | **Impact**: 9/10 | **Tag**: operational

**Required Sections**:

1. **Resource Constraints**: API limits, shared resources, budget targets
2. **Failure Modes**: Detection and recovery for each failure type
3. **Dynamic Adjustments**: Condition -> Action rules
4. **Shared Context**: What else uses these resources
5. **Stop Conditions**: When to self-terminate
