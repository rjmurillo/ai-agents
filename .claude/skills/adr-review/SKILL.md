---
name: adr-review
description: Multi-agent debate orchestration for Architecture Decision Records. Use when reviewing, validating, or refining ADRs. Triggers on "review this ADR", "validate ADR", "ADR debate", "critique this architecture decision", or when architect agent creates/updates an ADR. Coordinates architect, critic, independent-thinker, security, analyst, and high-level-advisor agents in structured debate rounds until consensus.
---

# ADR Review

Multi-agent debate pattern for rigorous ADR validation. Orchestrates 6 specialized agents through structured review rounds until consensus or 10 rounds maximum.

## When to Use

- User requests ADR review ("review this ADR", "validate this decision")
- Architect creates or updates an ADR
- Orchestrator detects ADR file changes
- Strategic decisions require multi-perspective validation

## Agent Roles

| Agent | Focus | Tie-Breaker Role |
|-------|-------|------------------|
| **architect** | Structure, governance, coherence, ADR compliance | Structural questions |
| **critic** | Gaps, risks, alignment, completeness | None |
| **independent-thinker** | Challenge assumptions, surface contrarian views | None |
| **security** | Threat models, security trade-offs | None |
| **analyst** | Root cause, evidence, feasibility | None |
| **high-level-advisor** | Priority, resolve conflicts, break ties | Decision paralysis |

## Debate Protocol

### Phase 1: Independent Review

Invoke each agent with the ADR content. Each provides:

```markdown
## [Agent] Review

### Strengths
- [What aspects are sound]

### Weaknesses/Gaps
- [What is missing, unclear, or problematic]

### Scope Concerns
- [Should this be split into multiple ADRs?]

### Questions
- [What needs clarification]

### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

P0 = blocking, P1 = important, P2 = nice-to-have
```

**Agent Invocation Pattern:**

```python
Task(subagent_type="architect", prompt="""
ADR Review Request (Phase 1: Independent Review)

## ADR Content
[Full ADR text]

## Instructions
1. Review for structural compliance with MADR 4.0
2. Check alignment with existing ADRs in .agents/architecture/ and docs/architecture/
3. Identify scope concerns (should this be split?)
4. Classify all issues as P0/P1/P2
5. Return structured review per Phase 1 format
""")
```

Repeat for: critic, independent-thinker, security, analyst, high-level-advisor.

### Phase 2: Consolidation

After all 6 reviews complete:

1. List consensus points (agents agree)
2. List conflicts (agents disagree)
3. Route conflicts to high-level-advisor for resolution
4. Categorize all issues by priority after rulings
5. Draft consolidated change recommendations

**Conflict Resolution Pattern:**

```python
Task(subagent_type="high-level-advisor", prompt="""
ADR Conflict Resolution Required

## Conflict 1: [Description]
- **architect position**: [Position]
- **security position**: [Position]
- Evidence: [Facts]

## Conflict 2: [Description]
...

## Decision Required
For each conflict, provide:
1. Which position prevails
2. Rationale
3. Whether ADR should be split
4. Final P0/P1/P2 classification
""")
```

### Phase 3: Resolution

1. Propose specific updates addressing P0 and P1 issues
2. Document dissenting views for "Alternatives Considered" section
3. Record rationale for incorporated vs rejected feedback
4. Generate complete updated ADR text

**Scope Split Detection:**

If 2+ agents flag scope concerns, recommend splitting:

```markdown
## Scope Split Recommendation

**Original ADR**: [Title]

**Proposed Split**:
1. ADR-NNN-A: [Focused decision 1]
2. ADR-NNN-B: [Focused decision 2]

**Rationale**: [Why splitting improves clarity and enforceability]
```

### Phase 4: Convergence Check

Re-invoke each agent to review proposed updates:

```python
Task(subagent_type="[agent]", prompt="""
ADR Convergence Check (Round [N])

## Updated ADR
[Full updated ADR text]

## Changes Made
[Summary of changes from Phase 3]

## Your Previous Concerns
[Agent's Phase 1 concerns]

## Instructions
Provide ONE position:
- **Accept**: No blocking concerns remain
- **Disagree and Commit**: Reservations exist but agree to proceed (document dissent)
- **Block**: Unresolved P0 concerns (specify what remains)
""")
```

**Consensus Criteria:**
- All 6 agents Accept OR Disagree-and-Commit = Consensus reached
- Any agent Blocks = Another round required (if round < 10)
- Round 10 with no consensus = Conclude with unresolved issues documented

## Round Management

```markdown
## Debate State

**Round**: [N] of 10
**Status**: [In Progress | Consensus | Concluded Without Consensus]

### Agent Positions
| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept/D&C/Block | [Brief note] |
| critic | Accept/D&C/Block | [Brief note] |
| independent-thinker | Accept/D&C/Block | [Brief note] |
| security | Accept/D&C/Block | [Brief note] |
| analyst | Accept/D&C/Block | [Brief note] |
| high-level-advisor | Accept/D&C/Block | [Brief note] |

### Unresolved Issues (if any)
[List P0 issues still blocking]
```

## Output Format

Save debate artifacts to `.agents/architecture/`:

### Debate Log

Save to: `.agents/architecture/ADR-NNN-debate-log.md`

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

### Updated ADR

Save to: `.agents/architecture/ADR-NNN-[title].md` (or update in place)

### Recommendations

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
```
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

## Efficiency Notes

- Most reviews converge in 1-2 rounds when high-level-advisor resolves conflicts early
- Skip Phase 1 re-invocation for agents with no relevant expertise (e.g., security for pure process ADRs)
- Cache agent positions between rounds to avoid re-reading unchanged concerns
