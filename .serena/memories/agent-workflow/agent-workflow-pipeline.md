# Full Pipeline for Large Changes

**Statement**: Use full agent pipeline for changes touching 10+ files

**Context**: Multi-file changes requiring coordination

**Evidence**: 2025-12-13 - 59-file change with zero rollbacks needed

**Atomicity**: 90%

**Impact**: 9/10

## Pipeline

```text
analyst → architect → planner → critic → implementer → qa → retrospective
```

## Agent-Appropriate Scope Selection

| Scope | Pipeline |
|-------|----------|
| 1-2 files, clear fix | implementer → qa |
| 3-10 files, defined change | planner → implementer → qa |
| 10+ files or new standards | full pipeline |
| Strategic decision | independent-thinker → high-level-advisor |

## Artifact Chain

```text
analysis/ → architecture/ → planning/ → critique/ → commits → qa/ → retrospective/ → skills/
```

Each agent produces artifacts that become inputs for the next agent.

## Related

- [agent-workflow-004-proactive-template-sync-verification](agent-workflow-004-proactive-template-sync-verification.md)
- [agent-workflow-005-structured-handoff-formats](agent-workflow-005-structured-handoff-formats.md)
- [agent-workflow-atomic-commits](agent-workflow-atomic-commits.md)
- [agent-workflow-collaboration](agent-workflow-collaboration.md)
- [agent-workflow-critic-gate](agent-workflow-critic-gate.md)
