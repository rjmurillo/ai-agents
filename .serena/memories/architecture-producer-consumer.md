# Skill-Architecture-004: Producer-Consumer Prompt Coordination

**Statement**: When updating agent workflows, modify both producer and consumer prompts

**Context**: Agent coordination architecture, workflow changes

**Evidence**: Session 17: Retrospective auto-handoff required coordinated updates to both retrospective.md (producer) and orchestrator.md (consumer)

**Atomicity**: 90%

**Impact**: 9/10

## Coordination Pattern

| Agent Role | File | Update Type |
|------------|------|-------------|
| Producer | retrospective.md | Define output format |
| Consumer | orchestrator.md | Parse and process format |

## Coordination Checklist

- [ ] Producer defines structured output (tables, sections, tokens)
- [ ] Consumer documents parsing logic
- [ ] Both prompts reference same field names/structure
- [ ] Example output provided in producer prompt
- [ ] Error handling defined in consumer prompt

## Anti-Pattern

Single-sided update breaks automation. Always update both.

## Related

- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
- [architecture-016-adr-number-check](architecture-016-adr-number-check.md)
- [architecture-adr-compliance-documentation](architecture-adr-compliance-documentation.md)
- [architecture-composite-action](architecture-composite-action.md)
