# Artifact Storage

Save debate artifacts to `.agents/critique/`.

## Debate Log

Save to: `.agents/critique/ADR-NNN-debate-log.md`

```markdown
# ADR Debate Log: [ADR Title]

## Summary
- **Rounds**: [N]
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

## Updated ADR

Save to: `.agents/architecture/ADR-NNN-[title].md` (or update in place)

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
- planner: Create implementation work packages
- task-generator: Break into atomic tasks
- None: ADR is informational only
```

## Integration Points

### Prior ADR Locations

Check these locations for existing ADRs and patterns:

- `.agents/architecture/ADR-*.md`
- `docs/architecture/ADR-*.md`

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
Review this ADR: .agents/architecture/ADR-005-api-versioning.md
```

**Orchestrator triggers:**

```python
# When architect creates/updates ADR
Task(subagent_type="orchestrator", prompt="""
Trigger adr-review skill for: .agents/architecture/ADR-005-api-versioning.md

Follow debate protocol in .claude/skills/adr-review/SKILL.md
""")
```
