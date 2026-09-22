# Evidence: critic review before implementation

<!-- placement: evidence; reason: records what a pre-implementation critic pass caught, not an operating contract -->

## Observed evidence

A critic review of a plan before implementation caught three minor issues
that would otherwise have surfaced as fix commits. The review checked
completeness, feasibility, scope, timeline, and risk coverage.

## Migration disposition

The `plan` skill runs the critic at its step 7, and the critic agent's Review
Axes and Verdict Rules own the criteria. The orchestrator agent's Routing
Algorithm places the critic plan gate before the implementer. This memory
keeps the three-issue outcome as evidence.
