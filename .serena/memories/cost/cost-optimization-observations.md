# Skill Observations: cost-optimization

**Last Updated**: 2026-09-19
**Sessions Analyzed**: 2 historical sessions plus a 30-day aggregate

## Purpose

This memory captures learnings from cost optimization strategies, token efficiency, and resource management across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

### 30-day agentic session cost profile

The main burn source is repeated long-context execution in `ai-agents`, not model output verbosity.

- 3,420 model calls recorded 488.0M tokens.
- 486.0M tokens were input; 471.6M, or 97.1%, were cached input.
- Median input was 141.8K tokens. P90 was 221.9K. Maximum was 248.8K.
- `exec` returned 36.5 MB across 3,849 calls.
- One PR #5844 thread consumed 302.7M tokens, 62% of the total, across 2,116 calls and 22 children. Its children added 125.5M tokens.
- Output was only 2.0M tokens, so repeated context and fanout are the dominant cost drivers.

The first control changes to evaluate are:

1. Make direct single-agent work the default. Delegate only when an independent merge artifact justifies it. Cap a task at 3 agents total and 2 concurrent agents.
2. Start a fresh thread for each phase instead of carrying one thread through investigation, implementation, review, and merge.
3. Bound `exec` output to summaries, names, counts, failures, and short excerpts.
4. Keep the universal runtime contract small. Load doctrine, review playbooks, and procedures only after workflow selection.
5. Run full validation once at final head. Do not repeat full gates after every intermediate edit unless the changed surface requires it.

These controls are evidence-backed priorities from the aggregate, not proof that every proposed limit is optimal. Measure token and outcome deltas after each change.

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Batch agent invocations for parallel operations reduce overall latency and cost (Session 2026-01-16-session-07, 2026-01-16)
- Use sonnet (not opus) for CI automation tasks - CI automation doesn't require orchestration capabilities, sonnet provides sufficient quality at lower cost (Session 3, PR #918, 2026-01-16)
  - Evidence: Changed model from opus to sonnet for CI automation workflow execution

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | MED | Batch agent invocations for parallel operations |
| 2026-01-16 | Session 3, PR #918 | MED | Use sonnet (not opus) for CI automation tasks |
| 2026-09-19 | 30-day agentic session aggregate | HIGH | Long-context repetition and delegation fanout dominate cost; prioritize direct work, bounded output, progressive disclosure, fresh phase threads, and final-head validation |

## Related

- [performance-observations](../quality/performance-observations.md)
- [architecture-observations](../architecture/architecture-observations.md)
- [agent-workflow-observations](../agent-workflow/agent-workflow-observations.md)
