# Implementation: Test Discovery

## Skill-Implementation-001: Pre-Implementation Test Discovery

**Statement**: Before implementing features, search for pre-existing test coverage.

**Context**: When assigned feature implementation task, before writing code.

**Evidence**: Serena transformation (2025-12-17): Tests existed in commit aa26328 but not discovered until after implementation. Test file `Sync-McpConfig.Tests.ps1` contained 3+ comprehensive test cases showing exact requirements.

**Atomicity**: 95%

**Impact**: 8/10 - Prevents duplicate work, clarifies requirements

## Skill-Implementation-002: Test-Driven Implementation

**Statement**: When tests pre-exist, run them first to understand feature expectations.

**Context**: After discovering pre-existing tests during test discovery phase.

**Evidence**: Serena transformation (2025-12-17): Three test cases under "Serena Transformation" context showed exact transformations needed:
- Transform `--context "claude-code"` to `"ide"`
- Transform `--port "24282"` to `"24283"`
- Transform both together

Running these tests first would have provided complete requirements specification.

**Atomicity**: 92%

**Impact**: 9/10 - Tests become executable requirements specification

## Pattern

1. Skill-Implementation-001: Discover if tests exist
2. Skill-Implementation-002: Run tests to understand requirements
3. Check templates need updates too
4. Then implement

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-006-graphql-first](implementation-006-graphql-first.md)
- [implementation-additive-approach](implementation-additive-approach.md)
