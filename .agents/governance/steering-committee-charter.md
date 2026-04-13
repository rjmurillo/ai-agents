# Agent System Steering Committee Charter

## Purpose

The Agent System Steering Committee governs the evolution of the multi-agent system, ensuring agents remain focused, non-overlapping, and effective. The committee reviews agent proposals, identifies consolidation opportunities, and maintains system health.

## Committee Composition

### Roles

| Role | Responsibility | Represented By |
|------|----------------|----------------|
| **Chair** | Meeting facilitation, final decisions | Project lead or designee |
| **Architect Representative** | Technical feasibility, design alignment | architect agent or human architect |
| **Security Representative** | Security implications | security agent or security engineer |
| **DevOps Representative** | Operational concerns | devops agent or platform engineer |
| **User Representative** | Developer experience | Active agent system user |

### Quorum

- Minimum 3 roles represented for decisions
- Chair must be present or delegate

## Meeting Cadence

### Regular Reviews

| Frequency | Focus | Agenda |
|-----------|-------|--------|
| Quarterly | System health review | Usage metrics, consolidation candidates, effectiveness |
| Monthly | New proposals | Review pending ADRs, approve/reject |
| Ad-hoc | Urgent issues | Routing failures, security concerns |

### Meeting Structure

1. **Review Period**: 30 minutes
   - Metrics review (if available)
   - Outstanding issues from previous meeting

2. **Proposal Review**: 45 minutes
   - New agent proposals
   - Consolidation proposals
   - Capability changes

3. **Decisions**: 15 minutes
   - Vote on proposals
   - Assign action items

## Decision Criteria

### New Agent Approval

All new agents must:

1. **Demonstrate unique value**: No > 20% overlap with existing agents
2. **Have clear entry criteria**: Answer "When should I use this?" in < 30 seconds
3. **Document limitations**: Explicit "what I cannot do" section
4. **Support composability**: Can work in agent chains
5. **Include success metrics**: Measurable outcomes

### Approval Workflow

```text
1. Proposer submits ADR using ADR-TEMPLATE.md
2. Chair assigns reviewers (min 2)
3. 1-week review period
4. Committee votes (majority wins)
5. If approved: Agent developed and documented
6. If rejected: Feedback provided, may resubmit
```

### Voting Rules

| Vote | Meaning | Effect |
|------|---------|--------|
| +1 | Approve | Counts toward approval |
| 0 | Abstain | No effect |
| -1 | Reject (with reason) | Blocks approval, must address |

- Approval requires: Majority +1, no unaddressed -1
- Chair breaks ties

## Consolidation Process

### Triggers for Consolidation Review

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Capability overlap | > 20% | Consolidation candidate |
| Low usage | < 5% monthly invocations | Review necessity |
| Routing confusion | > 3 misroutes/month | Clarify or merge |
| Maintenance burden | Single maintainer | Cross-train or merge |

### Consolidation Workflow

```text
1. Analyst identifies candidates using overlap analysis
2. Architect proposes consolidation ADR
3. Committee reviews (same as new agent)
4. If approved:
   a. Migration plan created
   b. 30-day deprecation notice
   c. Capabilities merged to surviving agent
   d. Old agent retired
   e. Documentation updated
```

### Migration Plan Requirements

- [ ] Capability mapping (old -> new)
- [ ] Documentation updates
- [ ] User notification
- [ ] Routing updates
- [ ] Interview protocol for merged agent

## Design Principles Enforcement

The committee enforces these principles (see agent-design-principles.md):

| Principle | Enforcement |
|-----------|-------------|
| Non-overlapping | Reject proposals with > 20% overlap |
| Clear entry criteria | Require objective criteria in ADR |
| Explicit limitations | Require "cannot do" section |
| Composable | Verify works in chains |
| Verifiable | Require success metrics |
| Consistent interface | Verify input/output format |

## Escalation Path

| Issue | First Responder | Escalation |
|-------|-----------------|------------|
| Routing conflict | Orchestrator | Architect, then Committee |
| Agent failure | QA | Analyst, then Committee |
| Security concern | Security | Committee immediately |
| Design conflict | Architect | Committee |
| Scope creep | Critic | Committee |

## Documentation Requirements

### Committee Produces

- Meeting minutes (stored in `.agents/governance/minutes/`)
- Decision log (stored in `.agents/governance/decisions/`)
- Quarterly health reports (stored in `.agents/governance/reports/`)

### Committee Maintains

- Agent catalog (CLAUDE.md agent table)
- Capabilities matrix (linked from capabilities)
- Design principles document
- This charter

## Amendment Process

Changes to this charter require:

1. Written proposal from committee member
2. 2-week comment period
3. Unanimous committee approval
4. Documentation update

## Related Documents

- [ADR Template](../architecture/ADR-TEMPLATE.md)
- [Agent Design Principles](./agent-design-principles.md)
- [Agent Consolidation Process](./agent-consolidation-process.md)
- [Agent Interview Protocol](./agent-interview-protocol.md)

---

*Charter Version: 1.0*
*Established: 2025-12-13*
*GitHub Issue: #8*
