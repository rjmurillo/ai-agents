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

## Skill-Implementation-003: Proactive Linting During File Creation (92%)

**Statement**: Run linters during file creation, not after implementation, to catch formatting issues early

**Context**: File creation workflow in multi-file implementations

**Trigger**: After creating or modifying markdown, YAML, or other lintable files

**Evidence**: Session 03 (2025-12-18): 7 MD040 errors caught post-implementation; all could have been prevented with immediate linting after file creation. Retrospective explicitly recommended this as process improvement.

**Atomicity**: 92%

- Specific action (run linters) ✓
- Single concept (timing of linting) ✓
- Actionable (trigger after Write) ✓
- Measurable (verify linter ran after each file) ✓
- Minor vagueness on "formatting issues" (-8%)

**Impact**: 7/10 - Prevents cosmetic fix commits

**Category**: Quality Workflow

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (AI Workflow Implementation session)

**Pattern**:

```bash
# After creating markdown file
npx markdownlint-cli2 path/to/file.md --fix

# After creating YAML workflow
actionlint .github/workflows/new-workflow.yml
```

---

## Skill-Implementation-004: Clarification Timing Optimization (97%)

**Statement**: Ask scope, authentication, and use case questions before planning starts, not during implementation

**Context**: Requirements gathering for multi-file or infrastructure changes

**Trigger**: Receiving implementation request with potential ambiguity

**Evidence**: Session 03 (2025-12-18): All clarifications asked at T+5 (before planning). Result: zero mid-implementation pivots, zero wasted effort.

**Atomicity**: 97%

- Specific question types ✓
- Specific timing (before planning) ✓
- Single concept (clarification timing) ✓
- Actionable (ask before planning) ✓
- Minor length: 14 words (-3%)

**Impact**: 9/10 - Prevents mid-stream pivots

**Category**: Planning Workflow

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (AI Workflow Implementation session)

**Questions to Ask Upfront**:

1. **Scope**: What's the boundary? This repo only? Which files?
2. **Authentication**: What credentials? Which secrets?
3. **Use Cases**: Which specific scenarios to support?
4. **Dependencies**: What external services/tools required?

---

## Skill-Implementation-005: Additive Feature Implementation (92%)

**Statement**: For features, add new sections rather than refactoring existing logic

**Context**: Feature implementation approach selection

**Trigger**: Implementing new feature in existing codebase

**Evidence**: Session 17 (2025-12-18): Retrospective auto-handoff feature added via new sections (Structured Handoff Output + Post-Retrospective Workflow) to `retrospective.md` and `orchestrator.md`. Result: 368 LOC added, zero bugs, zero retries, clean first-pass delivery. Commit `d7489ba` shows additive approach prevented regression risk.

**Atomicity**: 92%

- Specific action (add sections) ✓
- Single concept (additive vs. refactoring) ✓
- Actionable (clear implementation choice) ✓
- Measurable (can verify sections added vs. logic refactored) ✓
- Length: 10 words ✓

**Impact**: 9/10 - Reduces regression risk, enables faster delivery

**Category**: Implementation Strategy

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (Session 17 retrospective auto-handoff)

**Pattern**:

```markdown
# Existing Agent Prompt

## Existing Section 1
[existing logic]

## Existing Section 2
[existing logic]

## NEW FEATURE SECTION (Added)
[new feature logic isolated here]
```

**Anti-Pattern**:

```markdown
# Existing Agent Prompt

## Existing Section 1 (REFACTORED)
[mixed old + new logic - high regression risk]
```

---

## Related Documents

- Source: `.agents/retrospective/2025-12-17-serena-transformation-implementation.md`
- Source: `.agents/retrospective/2025-12-18-ai-workflow-implementation.md`
- Source: `.agents/sessions/2025-12-18-session-17-retrospective-auto-handoff.md`
- Related: skills-agent-workflow-phase3 (Skill-AgentWorkflow-004)
- Related: skills-qa (QA workflow skills)
- Related: skills-planning (Skill-Planning-003, Skill-Planning-004)
