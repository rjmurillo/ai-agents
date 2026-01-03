# ADR Debate Protocol

Detailed phases for multi-agent ADR validation.

## Phase 0: Related Work Research

Before launching independent reviews, use analyst agent to search for related work:

```text
Task(subagent_type="analyst", prompt="""
ADR Related Work Research

## ADR Being Reviewed
Title: [ADR title]
Key topics: [Extract 3-5 keywords from ADR]

## Research Tasks

1. **Search open Issues** for related discussions:
   ```bash
   gh issue list --state open --search "[keywords]" --json number,title,labels
   ```

2. **Search open PRs** for in-progress work:

   ```bash
   gh pr list --state open --search "[keywords]" --json number,title,headRefName
   ```

3. **Search closed Issues** for prior decisions:

   ```bash
   gh issue list --state closed --search "[keywords]" --limit 10 --json number,title,labels
   ```

## Output Format

### Related Issues

| # | Title | Status | Relevance |
|---|-------|--------|-----------|
| [number] | [title] | open/closed | [How it relates to ADR] |

### Related PRs

| # | Title | Branch | Status |
|---|-------|--------|--------|
| [number] | [title] | [branch] | [open/merged/closed] |

### Implications for ADR Review

- [What existing work affects this ADR?]
- [Are there gaps already known?]
- [Should any issues be linked?]
- [Are any PRs already implementing this?]
""")
```

Include related work findings in each Phase 1 agent prompt as context.

## Phase 1: Independent Review

Invoke each agent with the ADR content AND related work findings. Each provides:

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

## Phase 2: Consolidation

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

## Phase 3: Resolution

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

## Phase 4: Convergence Check

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
- **Disagree-and-Commit**: Reservations exist but agree to proceed (document dissent)
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

## Related Work Integration

When Phase 0 finds related items:

| Finding | Action |
|---------|--------|
| Open issue discussing same topic | Link in ADR, acknowledge in review |
| Closed issue with prior decision | Verify ADR aligns or documents deviation |
| Open PR implementing feature | Wait for PR or coordinate with author |
| Known gap in backlog | Verify ADR addresses the gap |
| Duplicate proposal | Consider closing in favor of existing |

## Efficiency Notes

- **Phase 0 is critical**: Related work research prevents duplicate effort and identifies existing gaps
- Most reviews converge in 1-2 rounds when high-level-advisor resolves conflicts early
- Skip Phase 1 re-invocation for agents with no relevant expertise (e.g., security for pure process ADRs)
- Cache agent positions between rounds to avoid re-reading unchanged concerns
- If Phase 0 finds an open PR already implementing the ADR, consider deferring review until PR is merged
