# Skill-Design-008: Semantic Precision in State Modeling

**Statement**: Acknowledged (reaction) ≠ Resolved (thread status) requires explicit lifecycle model

**Atomicity**: 95%

**Context**: When designing features with multi-state entities (comments, threads, PRs), create state diagrams to prevent semantic confusion

**Evidence**: PR #402 - NEW → ACKNOWLEDGED → REPLIED → RESOLVED model eliminated ambiguity

## When to Apply

**Trigger Conditions**:
- Designing features with multiple states
- State transitions depend on different conditions
- Multiple functions check state
- API provides partial state information

**Applies To**:
- GitHub PR comments (acknowledgment vs resolution)
- Issue workflows (new vs triaged vs assigned vs resolved)
- Review cycles (requested vs submitted vs approved)
- Bot response states (mentioned vs replied vs completed)

## How to Apply

1. **Identify States**: List all possible states for the entity
2. **Define Transitions**: Map state-to-state progression
3. **Specify Conditions**: Document exact checks for each state
4. **Separate Concerns**: Don't conflate distinct states (acknowledged ≠ resolved)
5. **Document Lifecycle**: Create diagram in design doc

## Example (PR #402)

**Problem**: Script conflated "acknowledged" (eyes reaction) with "resolved" (thread closed)

**Root Cause**: No explicit lifecycle model

**Solution**:
```text
NEW (eyes=0, unresolved)
  → ACKNOWLEDGED (eyes>0, unresolved)
  → REPLIED (eyes>0, unresolved, has reply)
  → RESOLVED (eyes>0, resolved)
```

**Outcome**: Zero confusion during implementation, critic approved on first attempt

## Anti-Patterns

❌ **Implicit States**: "Comment is either new or done"
✅ **Explicit States**: "Comment progresses: NEW → ACKNOWLEDGED → REPLIED → RESOLVED"

❌ **Compound Checks**: "If acknowledged then it's resolved"
✅ **Separate Checks**: "Acknowledged = eyes>0; Resolved = isResolved=true"

❌ **Boolean Flags**: "isDone = true/false"
✅ **State Machine**: "state ∈ {NEW, ACKNOWLEDGED, REPLIED, RESOLVED}"

## Related Skills

- **Skill-Design-007**: Lifecycle state diagrams prevent implementation ambiguity
- **Skill-Documentation-001**: Documentation-first approach
- **Skill-Planning-004**: Critic checkpoint before implementation

## Validation

**Metric**: Critic approval on first attempt = lifecycle model is clear

**Evidence**: PR #402 PRD approved without rework

**Impact**: High (zero semantic confusion = faster implementation)

## Tags

- design
- semantic-modeling
- state-machines
- lifecycle
- clarity

## Related

- [design-approaches-detailed](design-approaches-detailed.md)
- [design-by-contract](design-by-contract.md)
- [design-composability](design-composability.md)
- [design-diagrams](design-diagrams.md)
- [design-entry-criteria](design-entry-criteria.md)
