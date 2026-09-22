# Evidence: table handoffs removed a manual routing step

<!-- placement: evidence; reason: records one measured effect of structured handoffs, not an operating contract -->

## Observed evidence

Session 17 (2025-12-18): the retrospective auto-handoff feature emitted skill
candidates, memory updates, and git operations as tables. The orchestrator
parsed and routed them without human interpretation, which removed the manual
routing step that prose handoffs had required.

## Migration disposition

The orchestrator agent's Handoff Contract owns the delegation format, and
each role agent's `## Handoff` section owns what it returns. This memory
keeps the session 17 effect as evidence for the structured format.
