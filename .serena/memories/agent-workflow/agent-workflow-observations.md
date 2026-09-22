# Skill Observations: agent-workflow

<!-- placement: evidence; reason: session observations about multi-agent coordination, not an operating contract -->

**Last Updated**: 2026-09-21
**Sessions Analyzed**: 2

## Purpose

Learnings from agent coordination patterns, multi-agent workflows, and agent
collaboration strategies across sessions. The orchestrator agent and the
`autoplan` skill own the routing behavior; this file keeps the observations.

## Observations

- Multi-agent spec/plan review: Session 67 (2025-12-22) ran a 14-agent review
  of the Local Guardrails SPEC and PLAN and synthesized findings from
  architect, security, qa, analyst, and other agents before execution.
- Model selection for CI automation: Batch 37 (Session 4, 2026-01-16)
  configured CI automation with Sonnet rather than Opus to balance cost and
  capability. The routing policy in `AGENTS.md` now owns model selection.

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2025-12-22 | Session 67 | MED | Multi-agent spec/plan review pattern |
| 2026-01-16 | Session 4 | HIGH | Model selection for CI automation (Sonnet not Opus) |

## Related

- [agent-workflow-collaboration](agent-workflow-collaboration.md)
- [agent-workflow-critic-gate](agent-workflow-critic-gate.md)
- [agent-workflow-pipeline](agent-workflow-pipeline.md)
- [skills-agent-workflow-index](../skills-agent-workflow-index.md)
