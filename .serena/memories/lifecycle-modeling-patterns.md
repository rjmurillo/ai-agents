# Lifecycle Modeling Patterns

State machines for multi-state entities to prevent semantic confusion.

## PR Comment Lifecycle (PR #402)

**Discovered**: 2025-12-26 during PR #402 "Acknowledged vs Resolved" gap analysis

**States**:
```text
NEW (eyes=0, isResolved=false)
  → ACKNOWLEDGED (eyes>0, isResolved=false) 
  → REPLIED (eyes>0, isResolved=false, has reply)
  → RESOLVED (eyes>0, isResolved=true)
```

**State Checks**:
- **NEW**: `reactions.eyes = 0` AND `isResolved = false`
- **ACKNOWLEDGED**: `reactions.eyes > 0` AND `isResolved = false`
- **REPLIED**: `reactions.eyes > 0` AND `isResolved = false` AND `has reply`
- **RESOLVED**: `reactions.eyes > 0` AND `isResolved = true`

**Functions**:
- `Get-UnacknowledgedComments`: Detects NEW only (unacknowledged)
- `Get-UnaddressedComments`: Detects NEW + ACKNOWLEDGED + REPLIED (all unresolved)

**Key Insight**: **Acknowledged ≠ Resolved**
- Acknowledgment = eyes reaction added (human saw it)
- Resolution = thread marked resolved (issue fixed, thread closed)

**Implementation**: `scripts/Invoke-PRMaintenance.ps1` lines 588-753

**Documentation**: `.agents/architecture/bot-author-feedback-protocol.md`

## Pattern Benefits

1. **Eliminates Ambiguity**: Explicit states prevent "what does this mean?" questions
2. **Prevents Bugs**: PR #365 bug caused by conflating ACKNOWLEDGED with RESOLVED
3. **Guides Implementation**: Functions map directly to state checks
4. **Improves Testing**: Each state becomes a test case

## When to Use Lifecycle Models

- Multi-state entities (comments, threads, PRs, issues)
- Asynchronous workflows (bot responses, review cycles)
- State-dependent logic (different actions per state)
- API integrations (external state transitions)

## Template

```text
Entity: [Name]
States: [State1] -> [State2] -> [State3] -> [Final]

State Checks:
  [State1]: [Condition1] AND [Condition2]
  [State2]: [Condition3] AND [Condition4]
  ...

Functions:
  [Function1]: Detects [States]
  [Function2]: Detects [States]

Evidence: [PR/Issue number], [Outcome]
```

## Related Skills

- **Skill-Design-008**: Acknowledged (reaction) ≠ Resolved (thread status) requires explicit lifecycle model
- **Skill-Design-007**: Lifecycle state diagrams prevent implementation ambiguity

## Success Metrics

- **PR #402**: Zero semantic confusion during implementation
- **Critic Approval**: PRD approved on first attempt (lifecycle model clarity)
- **Live Validation**: All test fixtures matched lifecycle model exactly
