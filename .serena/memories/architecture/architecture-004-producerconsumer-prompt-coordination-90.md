# Architecture: Producerconsumer Prompt Coordination 90

## Skill-Architecture-004: Producer-Consumer Prompt Coordination (90%)

**Statement**: When updating agent workflows, modify both producer and consumer prompts

**Context**: Agent coordination architecture, workflow changes

**Trigger**: Updating agent handoff protocols or output formats

**Evidence**: Session 17 (2025-12-18): Retrospective auto-handoff feature required coordinated updates:
- Producer: `retrospective.md` - Added structured handoff output format (tables with skill/memory/git sections)
- Consumer: `orchestrator.md` - Added post-retrospective workflow to parse and process those tables

Single-sided update would break automation. Both prompts updated in commit `d7489ba`.

**Atomicity**: 90%

- Specific actors (producer and consumer) ✓
- Single concept (coordinated updates) ✓
- Actionable (modify both) ✓
- Measurable (verify both files changed) ✓
- Length: 10 words ✓

**Impact**: 9/10 - Prevents broken handoffs, enables automation

**Category**: Agent Coordination

**Tag**: helpful

**Created**: 2025-12-18

**Validated**: 1 (Session 17 retrospective auto-handoff)

**Pattern**:

| Agent Role | File | Update Type |
|------------|------|-------------|
| Producer | retrospective.md | Define output format |
| Consumer | orchestrator.md | Parse and process format |

**Coordination Checklist**:

- [ ] Producer defines structured output (tables, sections, tokens)
- [ ] Consumer documents parsing logic
- [ ] Both prompts reference same field names/structure
- [ ] Example output provided in producer prompt
- [ ] Error handling defined in consumer prompt

---

## Related

- [architecture-001-rolespecific-tool-allocation-92](architecture-001-rolespecific-tool-allocation-92.md)
- [architecture-002-model-selection-by-complexity-85](architecture-002-model-selection-by-complexity-85.md)
- [architecture-003-composite-action-pattern-for-github-actions-100](architecture-003-composite-action-pattern-for-github-actions-100.md)
- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
