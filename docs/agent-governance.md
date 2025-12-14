# Agent System Governance

## Overview

This document provides an overview of the governance framework for the multi-agent system. Governance ensures agents remain focused, non-overlapping, and effective as the system evolves.

## Governance Artifacts

| Artifact | Location | Purpose |
|----------|----------|---------|
| ADR Template | `.agents/architecture/ADR-TEMPLATE.md` | Template for agent decisions |
| Steering Committee Charter | `.agents/governance/steering-committee-charter.md` | Committee roles and processes |
| Agent Design Principles | `.agents/governance/agent-design-principles.md` | 6 principles all agents must follow |
| Consolidation Process | `.agents/governance/agent-consolidation-process.md` | How to merge overlapping agents |
| Interview Protocol | `.agents/governance/agent-interview-protocol.md` | Capability discovery process |

## The Six Design Principles

All agents must adhere to these principles:

1. **Non-Overlapping Specialization**: Maximum 20% capability overlap with other agents
2. **Clear Entry Criteria**: "Should I use this?" answerable in < 30 seconds
3. **Explicit Limitations**: Document what the agent CANNOT do
4. **Composability**: Work in agent chains without modification
5. **Verifiable Success**: Measurable success metrics
6. **Consistent Interface**: Standard input/output format

## Proposing New Agents

To propose a new agent:

1. Create an ADR using the template at `.agents/architecture/ADR-TEMPLATE.md`
2. Complete the overlap analysis (must be < 20%)
3. Document entry criteria, limitations, and success metrics
4. Submit for steering committee review
5. Implement after approval

## Consolidation Triggers

Agents are candidates for consolidation when:

| Trigger | Threshold |
|---------|-----------|
| Capability overlap | > 20% |
| Low usage | < 5% of invocations |
| Routing confusion | > 3 misroutes/month |
| Duplicate outputs | Same deliverable type |

## Steering Committee

The steering committee reviews proposals quarterly and includes:

- Chair (project lead)
- Architect representative
- Security representative
- DevOps representative
- User representative

Decisions require majority approval with no unaddressed objections.

## Agent Lifecycle

```text
PROPOSED -> APPROVED -> ACTIVE -> DEPRECATED -> RETIRED
    |           |          |           |
    v           v          v           v
 [ADR]     [Develop]  [Maintain]  [Archive]
```

## Quick Reference

### When to Create New Agent

- Unique capability gap identified
- < 20% overlap with existing agents
- Clear entry criteria definable
- Measurable success criteria

### When to Consolidate

- > 20% overlap with another agent
- Users confused about which to use
- Frequent misrouting by orchestrator
- Maintenance burden unsustainable

### When to Deprecate

- No longer provides unique value
- Superseded by better approach
- Usage dropped to negligible levels

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) - Agent catalog and workflows
- [Orchestrator Routing Algorithm](./orchestrator-routing-algorithm.md)
- [Task Classification Guide](./task-classification-guide.md)

---

*Governance Version: 1.0*
*Established: 2025-12-13*
*GitHub Issue: #8*
