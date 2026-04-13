# Agentworkflow: Proactive Template Sync Verification 95

## Skill-AgentWorkflow-004: Proactive Template Sync Verification (95%)

**Statement**: When modifying src/claude/ agent docs, verify templates/agents/ need same updates before committing

**Context**: Agent documentation changes across platforms

**Trigger**: Before committing changes to src/claude/*.md

**Evidence**: Phase 3 (P2) issue #44: P2-6 requirement (template porting) caught by user, not agent. User added P2-6 mid-execution after P2-1 through P2-5 completed because agent didn't proactively check template sync needs.

**Atomicity**: 95%

- Specific tool/location (src/claude/, templates/agents/) ✓
- Single concept (template sync verification) ✓
- Actionable (verify before commit) ✓
- Measurable (can check if done) ✓
- Length: 13 words ✓

**Category**: Agent Development Workflow

**Related Skills**:

- Skill-AgentWorkflow-001 (template-first workflow execution)
- Skill-AgentWorkflow-002 (Claude platform specifics)
- Skill-AgentWorkflow-003 (post-generation verification)

**Platforms**: Claude, VS Code, Copilot CLI

**Impact**: 9/10 - Prevents template drift proactively rather than reactively

**Tag**: helpful

**Created**: 2025-12-16

**Validated**: 2 (Phase 3 P2-6 pattern, Serena transformation 2025-12-17)

**Note**: Extended 2025-12-17 to include test verification, not just template sync. Serena transformation session showed tests can pre-exist and inform requirements. See Skill-Implementation-001 and Skill-Implementation-002 in skills-implementation memory.

---

## Relationship to Skill-AgentWorkflow-001

**Skill-AgentWorkflow-001**: Template-first workflow (EXECUTION)

- What: Update templates FIRST, then generate
- When: During implementation
- Focus: Correct sequence of operations

**Skill-AgentWorkflow-004**: Proactive template verification (PRE-FLIGHT)

- What: Check IF templates need updating BEFORE starting
- When: Before implementation begins
- Focus: Scope validation

**Pattern**: Use Skill-AgentWorkflow-004 during planning/scoping, then execute with Skill-AgentWorkflow-001 during implementation.

---