# Qa: Qa Agent Routing Decision 85

## Skill-QA-002: QA Agent Routing Decision (85%)

**Statement**: Route to qa agent after implementing features unless tests are comprehensive and passing

**Context**: After feature implementation, before commit

**Trigger**: Feature code complete

**Evidence**: Serena transformation (2025-12-17): Manual testing skipped qa agent workflow. Pattern observed in prior sessions where agents short-circuited workflow without clear criteria.

**Atomicity**: 85%

- Routing decision concept ✓
- Clear timing (after implementation) ✓
- Length: 12 words ✓
- Slightly vague "comprehensive" (-10%)

**Impact**: 7/10 - Ensures process consistency, clarifies when qa adds value

**Category**: QA Workflow

**Tag**: helpful

**Created**: 2025-12-17

**Validated**: 1 (Serena transformation pattern)

**Definition of "Comprehensive"**:
- Coverage >80%
- Multiple test cases per function
- Edge cases included
- Negative tests present
- Error handling verified

**When to Skip QA Agent** (exceptions to workflow):
- Tests are comprehensive (per definition above)
- All tests passing
- Change is trivial (docs, comments, formatting)

**When QA Agent is MANDATORY**:
- New features
- Complex logic
- Cross-platform concerns
- Security-sensitive code
- Breaking changes

---

## Related

- [qa-001-test-strategy-gap-checklist-90](qa-001-test-strategy-gap-checklist-90.md)
- [qa-007-worktree-isolation-verification](qa-007-worktree-isolation-verification.md)
- [qa-benchmark-script-validation](qa-benchmark-script-validation.md)
- [qa-session-protocol-validation-patterns](qa-session-protocol-validation-patterns.md)
- [qa-workflow-refactoring-patterns](qa-workflow-refactoring-patterns.md)
