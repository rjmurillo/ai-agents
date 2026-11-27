# The agent drift score is Jaccard on word sets, so repeated lines never move it

**Atomicity**: 90%
**Category**: Agent mirror drift checks
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E011. State checked on main at 1be533c496 (2026-11-26).

## Question

What does the agent drift score measure, and where does it fail?

## Conventional answer

Earlier rule text said the score saturates. It also used an idealized per section model, with every section scoring 100, to set the trip threshold.

## First-principles position

The score is Jaccard similarity on word sets. Repeated lines add no new words, so they never move it. New vocabulary does move it. A contradiction that reuses nearby vocabulary passes. Thresholds must come from measured per section scores.

## Evidence with limits

- Mutation test on the Constraints section of architect.md: 60 repeated identical lines scored 100.0.
- One line of distinct vocabulary scored 84.2. Sixty lines of distinct vocabulary scored 8.2, and the overall score stayed at 83.3, still OK.
- 22 of 26 agents trip on one rewritten section, and architect needs 2 rewritten sections, not 3 (2026-11-07).
- Limits: A single mutation shape on architect, measured between 2026-08-01 and 2026-11-07. The measurement was anchored in a Copilot session, because the other transcript held only the pasted rule text. It was not run on main.
- State on main at 1be533c496 (2026-11-26): fixed. .claude/rules/claude-agents.md line 105 states that 22 of 26 agents trip on one rewritten section, and line 109 states Jaccard on word sets.

## Decision

Compute drift thresholds from measured per section scores, never from an idealized 100 per section. Treat a high score as evidence of shared vocabulary only, not shared meaning.

## Related

- `.serena/memories/architecture/architecture-agent-mirror-two-pipeline.md`
- `.serena/memories/agents-two-pipeline-mirror-recipe.md`
