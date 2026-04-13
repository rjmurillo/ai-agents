# Agent Consolidation Process

## Purpose

This document defines the process for identifying, evaluating, and executing agent consolidations. Consolidation reduces system complexity, eliminates confusion, and maintains focus.

---

## Consolidation Triggers

### Automatic Review Triggers

| Trigger | Threshold | Detection Method |
|---------|-----------|------------------|
| High capability overlap | > 20% | Quarterly overlap audit |
| Low usage | < 5% of agent invocations | Usage metrics |
| Frequent misrouting | > 3 routing errors/month | Orchestrator logs |
| Duplicate outputs | Same deliverable type | Output analysis |
| Maintenance burden | Single point of failure | Ownership review |

### Manual Review Triggers

- User feedback indicating confusion
- Routing failures during orchestration
- New agent proposal with high overlap
- Organizational restructuring

---

## Phase 1: Identification

### Overlap Analysis

Perform capability comparison between candidates:

```markdown
## Overlap Analysis: [Agent A] vs [Agent B]

### Capability Comparison

| Capability | Agent A | Agent B | Overlap? |
|------------|---------|---------|----------|
| [Cap 1] | Yes/No | Yes/No | Yes/No |
| [Cap 2] | Yes/No | Yes/No | Yes/No |
| ... | ... | ... | ... |

### Overlap Calculation

- Total capabilities: [N]
- Overlapping capabilities: [M]
- Overlap percentage: [M/N * 100]%

### Differentiation

| Aspect | Agent A | Agent B |
|--------|---------|---------|
| Primary focus | [Focus] | [Focus] |
| Output type | [Type] | [Type] |
| Entry criteria | [Criteria] | [Criteria] |
```

### Recommendation Threshold

| Overlap % | Recommendation |
|-----------|----------------|
| 0-10% | No action |
| 11-20% | Clarify boundaries |
| 21-40% | Consider consolidation |
| 41-70% | Strong consolidation candidate |
| 71-100% | Consolidation required |

---

## Phase 2: Evaluation

### Impact Assessment

Evaluate consolidation impact:

```markdown
## Consolidation Impact: Merge [Agent A] into [Agent B]

### Affected Artifacts

| Artifact | Location | Change Required |
|----------|----------|-----------------|
| Agent definition | claude/[agent].md | Update capabilities |
| VS Code version | vs-code-agents/[agent].agent.md | Update capabilities |
| Copilot version | copilot-cli/[agent].agent.md | Update capabilities |
| Interview | .agents/governance/interviews/[agent]-interview.md | Re-interview |
| Orchestrator routing | docs/orchestrator-routing-algorithm.md | Update |

### User Impact

| User Type | Current Behavior | After Consolidation |
|-----------|------------------|---------------------|
| [Type] | [Behavior] | [New behavior] |

### Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| [Risk] | H/M/L | H/M/L | [Mitigation] |
```

### Decision Criteria

Consolidation should proceed if:

- [ ] Overlap > 20% confirmed
- [ ] Clear "surviving" agent identified
- [ ] All capabilities can be preserved or explicitly deprecated
- [ ] Migration path documented
- [ ] No critical dependencies blocked
- [ ] Stakeholder notification plan exists

---

## Phase 3: Planning

### Migration Plan Template

```markdown
## Migration Plan: [Agent A] -> [Agent B]

### Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Planning | 1 week | This document |
| Development | 1-2 weeks | Updated agent definitions |
| Deprecation notice | 30 days | User notification |
| Parallel operation | 2 weeks | Both agents available |
| Retirement | 1 day | Old agent removed |

### Capability Mapping

| Agent A Capability | Migrates To | Notes |
|-------------------|-------------|-------|
| [Capability] | Agent B / Deprecated | [Notes] |

### Documentation Updates

- [ ] Update surviving agent definition (all platforms)
- [ ] Update orchestrator routing
- [ ] Update interview protocol
- [ ] Update CLAUDE.md agent catalog
- [ ] Remove deprecated agent files
- [ ] Update any hardcoded references

### Communication Plan

| Audience | Message | Timing |
|----------|---------|--------|
| All users | Deprecation notice | Day 1 |
| Heavy users | Direct notification | Day 1 |
| All users | Migration guide | Day 7 |
| All users | Retirement notice | Day 30 |
```

---

## Phase 4: Execution

### Step 1: Update Surviving Agent

1. Add migrated capabilities to agent definition
2. Update all three platforms (Claude, VS Code, Copilot CLI)
3. Re-run interview protocol
4. Update capability documentation

### Step 2: Deprecation Notice

Add to deprecated agent:

```markdown
---
deprecated: true
deprecated_date: YYYY-MM-DD
successor: [surviving_agent_name]
---

> **DEPRECATED**: This agent is deprecated as of [date].
> Capabilities have been merged into **[surviving agent]**.
> This agent will be removed on [removal date].
```

### Step 3: Parallel Operation

- Both agents remain functional
- Monitor for issues
- Collect user feedback
- Adjust surviving agent if needed

### Step 4: Retirement

1. Remove deprecated agent files from all platforms
2. Update orchestrator routing to remove references
3. Archive agent documentation
4. Update agent catalog (CLAUDE.md)
5. Close related tracking issues

---

## Phase 5: Validation

### Post-Consolidation Checklist

```markdown
## Consolidation Validation: [Agent A] -> [Agent B]

### Functionality

- [ ] All Agent A capabilities work in Agent B
- [ ] No routing failures to deprecated agent
- [ ] Agent chains work correctly

### Documentation

- [ ] Agent catalog updated
- [ ] Routing algorithm updated
- [ ] Interview completed for merged agent
- [ ] All platform versions consistent

### Metrics

- [ ] No increase in routing errors
- [ ] No decrease in agent effectiveness
- [ ] User feedback addressed

### Cleanup

- [ ] Deprecated agent files removed
- [ ] No orphan references remain
- [ ] Archive created for historical reference
```

---

## Archive Structure

Retired agents are archived for reference:

```text
.agents/
  archive/
    retired-agents/
      [agent-name]/
        last-definition.md
        retirement-date.txt
        reason.md
        migration-to.txt
```

---

## Rollback Procedure

If consolidation causes issues:

1. **Assess**: Identify what's broken
2. **Revert**: Restore deprecated agent from archive
3. **Communicate**: Notify users of rollback
4. **Analyze**: Determine root cause
5. **Re-plan**: Create improved migration plan
6. **Retry**: Execute with fixes

---

## Example: Hypothetical Consolidation

### Scenario

`code-reviewer` agent overlaps 65% with `qa` agent.

### Analysis

| Capability | code-reviewer | qa | Action |
|------------|---------------|-----|--------|
| Code review | Yes | Yes | Merge to qa |
| Quality metrics | Yes | Yes | Merge to qa |
| Test strategy | No | Yes | Keep in qa |
| Defect analysis | Yes | No | Add to qa |
| Test execution | No | Yes | Keep in qa |

### Decision

Merge `code-reviewer` into `qa` because:

- 65% overlap (exceeds 20% threshold)
- `qa` has superset of core capabilities
- `code-reviewer` adds only defect analysis (easily merged)

### Outcome

- `qa` gains defect analysis capability
- `code-reviewer` deprecated and archived
- Routing updated to direct code reviews to `qa`

---

## Related Documents

- [Agent Design Principles](./agent-design-principles.md)
- [Steering Committee Charter](./steering-committee-charter.md)
- [ADR Template](../architecture/ADR-TEMPLATE.md)
- [Agent Interview Protocol](./agent-interview-protocol.md)

---

*Process Version: 1.0*
*Established: 2025-12-13*
*GitHub Issue: #8*
