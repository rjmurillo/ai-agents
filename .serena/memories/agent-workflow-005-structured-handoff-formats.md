# Skill-AgentWorkflow-005: Structured Handoff Formats

**Statement**: Use table formats for agent-to-agent handoffs to enable automation

**Context**: Agent coordination, handoff protocol design

**Trigger**: Designing output format for one agent to pass data to another

**Evidence**: Session 17 (2025-12-18): Retrospective auto-handoff feature uses table format for skill candidates, memory updates, and git operations. Structured format enables orchestrator to parse and route automatically without human interpretation. Example from `retrospective.md`:

```markdown
## Retrospective Handoff

### Skill Candidates
| ID | Statement | Atomicity | Context |
|----|-----------|-----------|------------|
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

**Related Skills**:

- Skill-Architecture-004: Producer-consumer prompt coordination (use together with this skill)
- Skill-CI-Structured-Output-001: Verdict tokens for CI automation (similar principle for CI/CD)

**Source**: Phase 3 Agent Workflow Skills (2025-12-16)
