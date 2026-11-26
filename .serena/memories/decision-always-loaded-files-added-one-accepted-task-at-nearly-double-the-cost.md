# In the v0.7.0 control ablation, always loaded files added one accepted task and raised cost per accepted task by 89 percent

**Atomicity**: 90%
**Category**: Eval design, context cost
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E031. State checked on main at 1be533c496 (2026-11-26).

## Question

Do always loaded instruction files raise the accepted task count enough to justify their cost?

## Conventional answer

Always loaded rules and instruction files improve agent outcomes, so loading them is worth the context cost.

## First-principles position

The control ablation did not show that. The files added one accepted task out of 15. Each accepted task cost almost twice as much with them. A one task gap is inside noise, so the gain is small and uncertain while the cost is measured.

## Evidence with limits

- Run on 2026-09-28, recorded in control-ablation-v0.7.0.md: 10 of 15 tasks accepted with the files, 9 of 15 without.
- Total model cost was $2.444 with the files and $1.163 without. Cost per accepted durable task was $0.244 and $0.129. The run without them cost 47 percent less per accepted task.
- Limits: One run on 2026-09-28 with claude-sonnet-5 and Claude Code 2.1.283, 15 runs per arm. A gap of one task is inside noise. Not shown for other models or tasks.
- State on main at 1be533c496 (2026-11-26): no repo artifact to fix. The record in control-ablation-v0.7.0.md is correct and labels the result MIXED. Its lines 47, 49, 65 and 66 carry the counts, costs and the 47 percent figure.

## Decision

Treat always loaded context as a measured cost with a small, uncertain gain. Justify each file with an ablation, not the belief that more instruction helps.

## Related

- `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`
