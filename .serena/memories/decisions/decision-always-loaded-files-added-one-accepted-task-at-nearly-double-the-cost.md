# In the v0.7.0 control ablation, always loaded files added one accepted run and raised cost per accepted run by 89 percent

**Atomicity**: 90%
**Category**: Eval design, context cost
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E031. State checked on main at 1be533c496 (2026-11-26).

## Question

Do always loaded instruction files raise the accepted task count enough to justify their cost?

## Conventional answer

Always loaded rules and instruction files improve agent outcomes, so loading them is worth the context cost.

## First-principles position

The control ablation did not show that. The study ran five tasks three times per arm. The files added one accepted run out of 15, and that run came from one approval-hold case. Each accepted run cost almost twice as much with them. The study set no noise bound, so the gain is small and uncertain while the cost is measured.

## Evidence with limits

- Run on 2026-09-28, recorded in control-ablation-v0.7.0.md: 10 of 15 runs accepted with the files, 9 of 15 without. Five tasks ran three times per arm. The extra run is `docs-title-publish`, the consequential hold case: 1 of 3 with the files, 0 of 3 without.
- Total model cost was $2.444 with the files and $1.163 without. Cost per accepted durable run was $0.244 and $0.129. The arm without them cost 47 percent less per accepted run.
- Limits: One run on 2026-09-28 with claude-sonnet-5 and Claude Code 2.1.283, 15 runs per arm. The record calls its numbers an observation, not a statistical bound (line 74), so no noise bound exists for a one run gap. Not shown for other models or tasks.
- State on main at 1be533c496 (2026-11-26): no repo artifact to fix. The record in control-ablation-v0.7.0.md is correct and labels the result MIXED. Its lines 47, 49, 61, 65 and 66 carry the counts, costs, the hold case and the 47 percent figure.

## Decision

Treat always loaded context as a measured cost with a small, uncertain gain. Justify each file with an ablation, not the belief that more instruction helps.

## Related

- `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`
