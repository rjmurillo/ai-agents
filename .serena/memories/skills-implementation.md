# Implementation Workflow Skills

**Extracted**: 2025-12-17
**Source**: `.agents/retrospective/2025-12-17-serena-transformation-implementation.md`

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

## Related Documents

- Source: `.agents/retrospective/2025-12-17-serena-transformation-implementation.md`
- Related: skills-agent-workflow-phase3 (Skill-AgentWorkflow-004)
- Related: skills-qa (QA workflow skills)
