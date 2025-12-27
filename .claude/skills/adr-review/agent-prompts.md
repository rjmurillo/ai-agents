<!-- markdownlint-disable MD024 MD040 MD051 -->
<!-- Disabled: MD024 (duplicate headings in code examples), MD040 (nested code blocks), MD051 (fragments in nested content) -->

# Agent Prompt Templates

Detailed prompt templates for each phase of ADR review.

## Table of Contents

1. [Phase 1: Independent Review Prompts](#phase-1-independent-review-prompts)
2. [Phase 2: Consolidation Prompts](#phase-2-consolidation-prompts)
3. [Phase 3: Resolution Prompts](#phase-3-resolution-prompts)
4. [Phase 4: Convergence Check Prompts](#phase-4-convergence-check-prompts)

---

## Phase 1: Independent Review Prompts

### Architect

```python
Task(subagent_type="architect", prompt="""
ADR Review Request (Phase 1: Independent Review)

**Role**: Technical authority on ADR structure and architectural coherence.

## ADR Content
```markdown
{adr_content}
```

## Prior ADRs Reference

Check alignment with existing decisions in:

- .agents/architecture/ADR-*.md
- docs/architecture/ADR-*.md

## Review Checklist

- [ ] MADR 4.0 structure compliance (frontmatter, required sections)
- [ ] Problem statement is clear and specific
- [ ] Decision drivers trace to requirements
- [ ] At least two genuine alternatives considered
- [ ] Pros/cons are balanced and evidence-based
- [ ] Justification references decision drivers
- [ ] Consequences include positive and negative
- [ ] Confirmation method is actionable
- [ ] Reversibility assessment completed
- [ ] Vendor lock-in assessed (if external dependencies)

## Scope Analysis

Does this ADR conflate multiple distinct decisions? Consider:

- Could this be split for clearer enforcement?
- Are there decisions that have different stakeholders?
- Would future teams benefit from separation?

## Output Format

### Strengths

- [Sound aspects with evidence]

### Weaknesses/Gaps

- [Issue]: [Why it matters]

### Scope Concerns

- [Split recommendation if applicable]

### Questions

- [Clarifications needed]

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

**You are the tie-breaker on structural/governance questions.**
""")

```

### Critic

```python
Task(subagent_type="critic", prompt="""
ADR Review Request (Phase 1: Independent Review)

**Role**: Stress-test the ADR for completeness, gaps, and alignment.

## ADR Content
```markdown
{adr_content}
```

## Review Focus

1. **Completeness**: Are all required sections present and filled?
2. **Feasibility**: Is the chosen option technically sound?
3. **Alignment**: Does this match project objectives and existing patterns?
4. **Testability**: Can the decision outcome be verified?
5. **Evidence**: Are claims supported by data or reasoning?

## Scope Analysis

Does this ADR try to address too many decisions at once?

- Think of ADRs like legislation: crisp decisions are easier to enforce
- Flag if splitting would improve clarity

## Output Format

### Strengths

- [What the ADR does well]

### Weaknesses/Gaps

- [Issue]: [Specific location in ADR]

### Scope Concerns

- [Split recommendation if applicable]

### Questions

- [Ambiguities requiring clarification]

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

**Focus on plan clarity, not execution details.**
""")

```

### Independent-Thinker

```python
Task(subagent_type="independent-thinker", prompt="""
ADR Review Request (Phase 1: Independent Review)

**Role**: Challenge assumptions and prevent groupthink.

## ADR Content
```markdown
{adr_content}
```

## Review Focus

1. **Challenge assumptions**: What is taken for granted without evidence?
2. **Alternative interpretations**: What other framings exist?
3. **Contrarian views**: What would critics of this decision say?
4. **Hidden risks**: What failure modes are not considered?
5. **Uncertainty areas**: Where is evidence weak or conflicting?

## Questions to Answer

- What evidence supports the key assumptions?
- Have we considered what happens if this decision is wrong?
- What alternative approaches were dismissed too quickly?
- Is there groupthink in the decision process?

## Output Format

### Strengths

- [Sound reasoning with evidence]

### Weaknesses/Gaps

- [Unchallenged assumption]: [Counter-evidence or alternative view]

### Scope Concerns

- [Split recommendation if applicable]

### Questions

- [Evidence gaps to address]

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

**Be the devil's advocate. Verify, don't validate.**
""")

```

### Security

```python
Task(subagent_type="security", prompt="""
ADR Review Request (Phase 1: Independent Review)

**Role**: Analyze security implications and threat models.

## ADR Content
```markdown
{adr_content}
```

## Security Review Checklist

- [ ] Attack surface changes identified
- [ ] New threat vectors assessed
- [ ] Security controls specified
- [ ] Authentication/authorization impact evaluated
- [ ] Data protection implications addressed
- [ ] Compliance implications noted
- [ ] Blast radius assessed
- [ ] Dependency security evaluated

## STRIDE Analysis (if applicable)

| Threat | Category | Impact | Likelihood | Mitigation |
|--------|----------|--------|------------|------------|
| [Threat] | S/T/R/I/D/E | H/M/L | H/M/L | [Control] |

## Output Format

### Strengths

- [Security-positive aspects]

### Weaknesses/Gaps

- [Security concern]: [Risk level and impact]

### Scope Concerns

- [Split recommendation if security scope is mixed]

### Questions

- [Security clarifications needed]

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

**Assume breach, design for defense.**
""")

```

### Analyst

```python
Task(subagent_type="analyst", prompt="""
ADR Review Request (Phase 1: Independent Review)

**Role**: Validate claims with evidence and assess feasibility.

## ADR Content
```markdown
{adr_content}
```

## Review Focus

1. **Evidence validation**: Are claims supported by data?
2. **Feasibility assessment**: Can this be implemented as described?
3. **Dependency analysis**: Are dependencies correctly identified?
4. **Risk assessment**: Are risks realistic and mitigations adequate?
5. **Cost/benefit**: Is the trade-off analysis accurate?

## Research Questions

- What evidence supports the claimed benefits?
- Are the effort estimates realistic based on similar work?
- What prior art or industry patterns apply?
- What are the known failure modes for this approach?

## Output Format

### Strengths

- [Well-supported claims with evidence]

### Weaknesses/Gaps

- [Unsupported claim]: [What evidence is missing]

### Scope Concerns

- [Split recommendation if applicable]

### Questions

- [Research questions to address]

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

**Distinguish facts from hypotheses.**
""")

```

### High-Level-Advisor

```python
Task(subagent_type="high-level-advisor", prompt="""
ADR Review Request (Phase 1: Independent Review)

**Role**: Strategic assessment and priority validation.

## ADR Content
```markdown
{adr_content}
```

## Strategic Review Focus

1. **Alignment**: Does this support strategic objectives?
2. **Priority**: Is this the right decision at the right time?
3. **Trade-offs**: Are the trade-offs appropriate for current context?
4. **Scope**: Is the decision appropriately sized?
5. **Reversibility**: What happens if we need to change course?

## Key Questions

- Is this solving the right problem?
- What are we giving up by making this decision?
- What should we stop doing if we proceed?
- Is there a simpler approach being overlooked?

## Output Format

### Strengths

- [Strategic alignment with evidence]

### Weaknesses/Gaps

- [Strategic concern]: [Impact on objectives]

### Scope Concerns

- [Split recommendation if applicable]

### Questions

- [Strategic clarifications needed]

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

**You break ties between other agents. Deliver verdicts, not options.**
""")

```

---

## Phase 2: Consolidation Prompts

### Conflict Resolution

```python
Task(subagent_type="high-level-advisor", prompt="""
ADR Conflict Resolution Required

## ADR Under Review
{adr_title}

## Agent Reviews Summary
{agent_reviews_summary}

## Conflicts Requiring Resolution

### Conflict 1: {conflict_description}
- **{agent_a}**: {position_a}
  - Evidence: {evidence_a}
- **{agent_b}**: {position_b}
  - Evidence: {evidence_b}

### Conflict 2: {conflict_description}
...

## Decisions Required
For each conflict:
1. Which position prevails and why
2. Is this truly P0 (blocking) or can it be P1?
3. Should the ADR be split to resolve scope conflicts?
4. What specific change resolves this?

## Scope Split Decision
If 2+ agents flagged scope concerns:
- Should this ADR be split? [Yes/No]
- If yes, how should it be divided?

## Output Format
### Conflict Resolutions

#### Conflict 1: {description}
- **Ruling**: {prevailing_position}
- **Rationale**: {why}
- **Priority**: {P0/P1/P2}
- **Required Change**: {specific_change}

### Scope Decision
- **Split Required**: [Yes/No]
- **Split Proposal**: [If yes, describe]

### Final Priority Classification
| Issue | Priority | Owner | Status |
|-------|----------|-------|--------|
| [Issue] | P0/P1/P2 | [Agent] | [Open/Resolved] |
""")
```

---

## Phase 3: Resolution Prompts

### ADR Update Generation

```python
# Orchestrator generates updated ADR based on consolidated feedback
# No agent invocation needed - orchestrator synthesizes

## Resolution Checklist
- [ ] All P0 issues addressed with specific changes
- [ ] All P1 issues addressed or documented as accepted
- [ ] Dissenting views captured in "Alternatives Considered"
- [ ] Decision rationale documents why feedback was incorporated/rejected
- [ ] Complete ADR text generated (not just diff)
```

---

## Phase 4: Convergence Check Prompts

### Convergence Template (All Agents)

```python
Task(subagent_type="{agent}", prompt="""
ADR Convergence Check (Round {round_number})

## Updated ADR
```markdown
{updated_adr_content}
```

## Changes Made This Round

{changes_summary}

## Your Previous Concerns

{agent_previous_concerns}

## Resolution Status

| Your Concern | Resolution | Addressed? |
|--------------|------------|------------|
| {concern} | {resolution} | {status} |

## Instructions

Provide exactly ONE position:

**Accept**: All blocking concerns resolved. No new issues found.

**Disagree-and-Commit**: Reservations remain but I agree to proceed.

- Must document specific dissent
- Dissent will be recorded in ADR

**Block**: Unresolved P0 concerns prevent acceptance.

- Must specify exactly what remains unaddressed
- Must explain why this is blocking

## Output Format

**Position**: [Accept | Disagree-and-Commit | Block]

**Rationale**: [Why this position]

**Dissent** (if D&C): [Specific reservations for the record]

**Blocking Issues** (if Block): [Exact P0 issues remaining]
""")

```

---

## Scope Split Templates

### Split Recommendation

```markdown
## Scope Split Recommendation

**Original ADR**: {original_title}
**Original Path**: {original_path}

### Problem
This ADR conflates {N} distinct decisions:
1. {decision_1}
2. {decision_2}
{additional_decisions}

### Proposed Split

#### ADR-{NNN}-A: {focused_title_1}
**Scope**: {what_this_covers}
**Stakeholders**: {who_cares}
**Dependencies**: {what_must_exist_first}

#### ADR-{NNN}-B: {focused_title_2}
**Scope**: {what_this_covers}
**Stakeholders**: {who_cares}
**Dependencies**: {what_must_exist_first}

### Rationale
- Clearer enforcement boundaries
- Different stakeholder groups
- Different review/approval timelines
- Easier future reference

### Migration Plan
1. Create ADR-{NNN}-A with {scope}
2. Create ADR-{NNN}-B with {scope}
3. Mark original ADR as "superseded by ADR-{NNN}-A and ADR-{NNN}-B"
4. Update cross-references in dependent ADRs
```
