# Implementation: Preimplementation Test Discovery 95

## Skill-Implementation-001: Pre-Implementation Test Discovery (95%)

**Statement**: Before implementing features search for pre-existing test coverage

**Context**: When assigned feature implementation task, before writing code

**Trigger**: Feature implementation request received

**Evidence**: Serena transformation (2025-12-17): Tests existed in commit aa26328 but not discovered until after implementation. Test file `Sync-McpConfig.Tests.ps1` contained 3+ comprehensive test cases for serena transformation that showed exact requirements.

**Atomicity**: 95%

- Specific action (search for tests) ✓
- Single concept ✓
- Actionable (search before implementation) ✓
- Measurable (can verify search was performed) ✓
- Length: 7 words ✓

**Impact**: 8/10 - Prevents duplicate work, clarifies requirements

**Category**: Implementation Workflow

**Tag**: helpful

**Created**: 2025-12-17

**Validated**: 1 (Serena transformation pattern)

---

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-001-preimplementation-test-discovery](implementation-001-preimplementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-002-testdriven-implementation-92](implementation-002-testdriven-implementation-92.md)
