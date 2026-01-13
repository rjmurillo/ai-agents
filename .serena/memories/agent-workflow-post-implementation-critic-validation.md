# Skill-AgentWorkflow-006: Post-Implementation Critic Validation

**Statement**: Invoke critic agent after changes involving naming, formatting, or architectural standards for compliance validation

**Context**: After implementing changes that touch conventions, standards, or patterns

**Trigger**: Changes made to files with established conventions (naming, formatting, ADR compliance)

**Evidence**: Session 87 - After renaming `.claude/commands/pr-review.md`, claimed work complete. User invoked critic which found non-compliance (missing numeric IDs). Required fix commit 5a65f65.

**Atomicity**: 90%

- Specific context (after implementation) ✓
- Single concept (post-change validation) ✓
- Actionable (invoke critic) ✓
- Measurable (critic returns PASS/FAIL) ✓
- Length: 14 words ✓

**Category**: Agent Development Workflow

**Impact**: 8/10 - Prevents non-compliant changes from reaching main

## Pattern

```python
# After making changes to convention-governed files
Task(subagent_type="critic", prompt="Validate changes in [file] against [standard]")
```

**Example triggers**:
- Modifying skill file formats
- Renaming files following naming conventions
- Updating ADR-governed patterns
- Changing protocol templates

## Why It Matters

Self-review misses compliance issues that critic catches objectively. Critic validates against documented standards without implementer bias.

## Related Skills

- **Complements**: [agent-workflow-critic-gate](agent-workflow-critic-gate.md) (pre-implementation plan validation)
- **BLOCKS**: None - This is post-implementation safety net
- **ENABLES**: Higher quality merges, fewer fix commits

## Related

- [agent-workflow-004-proactive-template-sync-verification](agent-workflow-004-proactive-template-sync-verification.md)
- [agent-workflow-005-structured-handoff-formats](agent-workflow-005-structured-handoff-formats.md)
- [agent-workflow-atomic-commits](agent-workflow-atomic-commits.md)
- [agent-workflow-collaboration](agent-workflow-collaboration.md)
- [agent-workflow-critic-gate](agent-workflow-critic-gate.md)
