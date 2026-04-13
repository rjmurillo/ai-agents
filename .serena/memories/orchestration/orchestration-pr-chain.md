# Skill-Orchestration-004: PR Comment Response Chain

**Statement**: For PR review feedback, use orchestrator → retrospective → pr-comment-responder chain

**Context**: PR has review comments (bot or human) that need addressing

**Evidence**: Session 56: Chain extracted Skill-PowerShell-005 before addressing 20 review threads

**Atomicity**: 90%

**Impact**: 9/10

## Workflow

```text
1. orchestrator identifies PR with review comments
2. Spawns retrospective agent → extracts skills/learnings
3. retrospective updates memories (skills-*, retrospective/*)
4. Spawns pr-comment-responder with context
5. pr-comment-responder addresses all review threads
6. Updates HANDOFF with outcomes
```

## Why This Order

Retrospective extracts learnings while context is fresh. Skills captured before tactical fixes. Institutional knowledge preserved.

## Anti-Pattern

Jumping straight to pr-comment-responder - loses learning opportunity.

## Related

- [orchestration-003-orchestrator-first-routing](orchestration-003-orchestrator-first-routing.md)
- [orchestration-copilot-swe-anti-patterns](orchestration-copilot-swe-anti-patterns.md)
- [orchestration-handoff-coordination](orchestration-handoff-coordination.md)
- [orchestration-parallel-execution](orchestration-parallel-execution.md)
- [orchestration-process-workflow-gaps](orchestration-process-workflow-gaps.md)
