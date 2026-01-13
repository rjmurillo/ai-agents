# Skill-Orchestration-003: Handoff Validation Gate

**Statement**: Orchestrator MUST validate Session End checklist before accepting agent handoff

**Context**: Before orchestrator accepts handoff from specialized agent

**Evidence**: Mass failure (2025-12-20): 23 of 24 agents handed off without Session End checklist complete

**Atomicity**: 92%

**Impact**: 10/10 (CRITICAL)

## Acceptance Criteria

1. Session log exists at `.agents/sessions/YYYY-MM-DD-session-NN.json`
2. `Validate-SessionEnd.ps1` passes (exit code 0)
3. Agent provides validation evidence in handoff output

## Rejection Response

```markdown
HANDOFF REJECTED: Session End checklist incomplete

**Validation**: FAIL - 3 unchecked requirements
  - [ ] HANDOFF.md update
  - [ ] Markdown lint
  - [ ] Commit changes

**Required action**: Complete checklist, then re-handoff.
```

## Acceptance Response

```markdown
HANDOFF ACCEPTED: Session End protocol compliant

**Validation**: PASS - All requirements complete
**Commit SHA**: 3b6559d
```
