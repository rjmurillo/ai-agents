# Artifact Storage

Save debate artifacts to `.project-toolkit/critique/`.

## Debate Log

The first debate on an ADR saves to the path below. Each later debate
(N = 2, 3, ...) saves to `.project-toolkit/critique/ADR-NNN-debate-log-2.md`
(`-3`, and so on) and never overwrites a closed log.

Save to: `.project-toolkit/critique/ADR-NNN-debate-log.md`

```markdown
# ADR Debate Log: [ADR Title]

## Summary
- **Rounds**: [N] of 10
- **Prior debate log**: none (otherwise the path of the closed log this debate follows)
- **Outcome**: [Consensus | Concluded Without Consensus]
- **Final Status**: [proposed | accepted | needs-revision]

## Round [N] Summary

### Key Issues Addressed
- [Issue 1]
- [Issue 2]

### Major Changes Made
- [Change 1]
- [Change 2]

### Agent Positions
| Agent | Position |
|-------|----------|
| ... | ... |

### Next Steps
[If applicable]
```

Rounds number from 1 within this log and never continue across logs. See
`debate-protocol.md#round-cap`.

## Updated ADR

Save to: `.project-toolkit/architecture/ADR-NNN-[title].md` (or update in place)

## Recommendations

Return to orchestrator with structured recommendations:

```markdown
## ADR Review Complete

**ADR**: [Path]
**Consensus**: [Yes/No]
**Rounds**: [N]

### Outcome
- **Status**: [accepted | needs-revision | split-recommended]
- **Updated ADR**: [Path to updated file]
- **Debate Log**: [Path to debate log]

### Scope Split (if applicable)
[Details of recommended splits]

### Planning Recommendations
[If ADR accepted and implementation planning needed]

**Recommend orchestrator routes to**:
- milestone-planner: Create implementation work packages
- task-decomposer: Break into atomic tasks
- None: ADR is informational only
```

## Integration Points

### Prior ADR Locations

Check these locations for existing ADRs and patterns:

- `.project-toolkit/architecture/ADR-*.md`
- `docs/adr/ADR-*.md`
- `docs/architecture/ADR-*.md`
- `docs/decisions/ADR-*.md`
- `architecture/decisions/ADR-*.md`

### ADR Template Reference

Use MADR 4.0 format per architect.md. Key sections:

- Context and Problem Statement
- Decision Drivers
- Considered Options
- Decision Outcome (with Consequences and Confirmation)
- Pros and Cons of Options

### Reversibility Assessment

Every ADR must include reversibility assessment per architect.md:

- Rollback capability
- Vendor lock-in assessment
- Exit strategy
- Legacy impact
- Data migration reversibility

## Example Invocation

**User triggers:**

```text
Review this ADR: .project-toolkit/architecture/ADR-005-api-versioning.md
```

**Orchestrator triggers:**

```python
# When architect creates/updates ADR
task(
    agent_type="project-toolkit:orchestrator",
    prompt="""
Trigger adr-review skill for: .project-toolkit/architecture/ADR-005-api-versioning.md

Follow debate protocol in .claude/skills/adr-review/SKILL.md
""",
)
```

<!-- vendor-portability: declared. This doc directs debate artifacts to .project-toolkit/critique/ and accepted ADRs to .project-toolkit/architecture/. In a vendored install without those dirs the agent creates them (or writes to the consumer's chosen artifact root); the paths are write targets, not preconditions. Issue #2050. -->
