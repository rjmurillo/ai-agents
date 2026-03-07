# Implementation: Testdriven Implementation 92

## Skill-Implementation-002: Test-Driven Implementation (92%)

**Statement**: When tests pre-exist run them first to understand feature expectations

**Context**: After discovering pre-existing tests during test discovery phase

**Trigger**: Tests found before implementation starts

**Evidence**: Serena transformation (2025-12-17): Three test cases in `Sync-McpConfig.Tests.ps1` under "Serena Transformation" context showed exact transformations needed:
- Transform `--context "claude-code"` to `"ide"`
- Transform `--port "24282"` to `"24283"`
- Transform both together

Running these tests first would have provided complete requirements specification.

**Atomicity**: 92%

- Specific action (run tests first) ✓
- Single concept ✓
- Actionable (clear timing) ✓
- Measurable (can verify tests were run) ✓
- Length: 11 words ✓

**Impact**: 9/10 - Tests become executable requirements specification

**Category**: Test-Driven Development

**Tag**: helpful

**Created**: 2025-12-17

**Validated**: 1 (Serena transformation pattern)

---

## Relationship to Existing Skills

### Skill-AgentWorkflow-004 (Updated)

**Original**: "When modifying src/claude/ agent docs, verify templates/agents/ need same updates before committing"

**Updated (2025-12-17)**: "Before implementation verify templates and tests for existing artifacts requiring updates"

**Why Extended**: Original was too narrow (agent docs only). Serena transformation showed tests also need verification during pre-implementation phase.

**Pattern**: Use both skills together:
1. Skill-Implementation-001: Discover if tests exist
2. Skill-Implementation-002: Run tests to understand requirements
3. Skill-AgentWorkflow-004: Check templates need updates too
4. Then implement

---

## Related

- [implementation-001-memory-first-pattern](implementation-001-memory-first-pattern.md)
- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-001-preimplementation-test-discovery-95](implementation-001-preimplementation-test-discovery-95.md)
- [implementation-001-preimplementation-test-discovery](implementation-001-preimplementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
