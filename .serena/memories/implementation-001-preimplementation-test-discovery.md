# Implementation: Preimplementation Test Discovery

## Skill-Implementation-001: Pre-Implementation Test Discovery

**Statement**: Before implementing features, search for pre-existing test coverage.

**Context**: When assigned feature implementation task, before writing code.

**Evidence**: Serena transformation (2025-12-17): Tests existed in commit aa26328 but not discovered until after implementation. Test file `Sync-McpConfig.Tests.ps1` contained 3+ comprehensive test cases showing exact requirements.

**Atomicity**: 95%

**Impact**: 8/10 - Prevents duplicate work, clarifies requirements

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-001-preimplementation-test-discovery-95](implementation-001-preimplementation-test-discovery-95.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-002-testdriven-implementation-92](implementation-002-testdriven-implementation-92.md)
