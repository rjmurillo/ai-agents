# Skill-Implementation-005: Additive Feature Implementation

**Statement**: For features, add new sections rather than refactoring existing logic.

**Context**: Feature implementation approach selection.

**Evidence**: Session 17 (2025-12-18): Retrospective auto-handoff feature added via new sections to `retrospective.md` and `orchestrator.md`. Result: 368 LOC added, zero bugs, zero retries, clean first-pass delivery. Commit `d7489ba` shows additive approach prevented regression risk.

**Atomicity**: 92%

**Impact**: 9/10 - Reduces regression risk, enables faster delivery

## Good Pattern

```markdown
# Existing Agent Prompt

## Existing Section 1
[existing logic]

## Existing Section 2
[existing logic]

## NEW FEATURE SECTION (Added)
[new feature logic isolated here]
```

## Anti-Pattern

```markdown
# Existing Agent Prompt

## Existing Section 1 (REFACTORED)
[mixed old + new logic - high regression risk]
```

## Why Additive Works

- Existing tests continue to pass
- New feature isolated for easy debugging
- Rollback is simple (remove section)
- Code review focuses on additions only

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-006-graphql-first](implementation-006-graphql-first.md)
- [implementation-clarification](implementation-clarification.md)
