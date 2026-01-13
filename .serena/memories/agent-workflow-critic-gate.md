# Pre-Implementation Validation Gate

**Statement**: Always run critic validation on plans before implementation begins

**Context**: Before implementing from any plan

**Evidence**: Critic review caught 3 minor issues before implementation

**Atomicity**: 92%

**Impact**: 9/10

## Validation Criteria

- **Completeness**: All requirements covered?
- **Feasibility**: Can be implemented as specified?
- **Scope**: Bounded appropriately?
- **Timeline**: Realistic estimates?
- **Risks**: Identified and mitigated?

## Anti-Pattern

Never skip critic review for changes affecting more than 5 files.

**Prevention**: Critic review is required gate for systemic changes.

## Related

- [agent-workflow-004-proactive-template-sync-verification](agent-workflow-004-proactive-template-sync-verification.md)
- [agent-workflow-005-structured-handoff-formats](agent-workflow-005-structured-handoff-formats.md)
- [agent-workflow-atomic-commits](agent-workflow-atomic-commits.md)
- [agent-workflow-collaboration](agent-workflow-collaboration.md)
- [agent-workflow-mvp-shipping](agent-workflow-mvp-shipping.md)
