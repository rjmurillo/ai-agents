# Agent Workflow Skills - Phase 3

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase3-p2-learnings.md`

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

## Skill-AgentWorkflow-005: Structured Handoff Formats (88%)

**Statement**: Use table formats for agent-to-agent handoffs to enable automation

**Context**: Agent coordination, handoff protocol design

**Trigger**: Designing output format for one agent to pass data to another

**Evidence**: Session 17 (2025-12-18): Retrospective auto-handoff feature uses table format for skill candidates, memory updates, and git operations. Structured format enables orchestrator to parse and route automatically without human interpretation. Example from `retrospective.md`:

```markdown
## Retrospective Handoff

### Skill Candidates
| ID | Statement | Atomicity | Context |
|----|-----------|-----------|---------|
| Skill-X-001 | [statement] | 92% | [context] |

### Memory Updates
| File | Update Type | Content |
|------|-------------|---------|
| skills-x.md | ADD | [skill] |
```

Machine-parseable structure eliminated manual routing step.

**Atomicity**: 88%

- Specific format (tables) ✓
- Single concept (structured handoffs) ✓
- Actionable (use tables) ✓
- Measurable (verify table format used) ✓
- Minor vagueness on "enable automation" (-12% for outcome vs. action)

**Impact**: 9/10 - Enables automatic processing, reduces manual handoff errors

**Category**: Agent Coordination

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (Session 17 retrospective auto-handoff)

**Pattern**:

**Good** (Machine-parseable):

```markdown
## Handoff to Next Agent

| Field | Value |
|-------|-------|
| Task | [specific task] |
| Input | [input data] |
| Context | [context] |
```

**Bad** (Prose):

```markdown
## Handoff to Next Agent

Please review the findings above and consider adding them to the skillbook.
```

**Table Format Guidelines**:

1. Use consistent column headers across agents
2. Include field names that consumer expects
3. Provide example row in producer prompt
4. Document parsing logic in consumer prompt

---

## Related Skills

**Skill-Architecture-004**: Producer-consumer prompt coordination (use together with this skill)
**Skill-CI-Structured-Output-001**: Verdict tokens for CI automation (similar principle for CI/CD)

**Pattern**: Use Skill-AgentWorkflow-004 during planning/scoping, then execute with Skill-AgentWorkflow-001 during implementation.
