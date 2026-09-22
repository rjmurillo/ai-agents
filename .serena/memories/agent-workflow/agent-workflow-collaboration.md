# Evidence: a mid-execution user addition exposed a scope gap

<!-- placement: evidence; reason: records one incident where a user addition revealed a missing heuristic, not an operating contract -->

## Observed evidence

Phase 3 (P2) of issue #44 scoped P2-1 through P2-5 as `src/claude/` edits.
The user added P2-6 (template porting) mid-execution because the agent did
not check whether the agent templates needed the same change. The addition
improved the outcome and showed the missing heuristic: an agent doc change
implies a template check. That heuristic is now moot; ADR-109 B1 renders
`.claude/agents/` from `templates/agents/`, so the template is the only edit.

## Migration disposition

The `reflect` skill owns capturing a user correction or addition as a
learning. This memory keeps the P2-6 incident as evidence that a user
addition is a knowledge-gap signal, not an interruption.
