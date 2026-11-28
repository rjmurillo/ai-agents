# Moving rules into skill references lowered scores in 11 of 21 trials because routing often picked no skill

**Atomicity**: 90%
**Category**: Rule eval, skill routing
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E073. State checked on main at 1be533c496 (2026-11-26).

## Question

Does folding an always-on rule into a skill reference keep behavior while cutting tokens?

## Conventional answer

A context diet that turns always-on rules into on-demand skill references keeps behavior and cuts tokens.

## First-principles position

The folded text survived. The post-diet full arm matched the pre-diet full arm. Routing failed. The first hop picked no skill, even when only the target skill was offered. The routed arm lost capability in 11 of 21 moves. Rule text alone does not carry the behavior if the model never opens the skill.

## Evidence with limits

- On Sonnet 5.5 with 143 scenarios (2026-11-24), the post-diet full arm matched the pre-diet full arm in every move.
- The routed arm lost 0.66 to 2.27 points in 11 of 21 moves.
- Security scored 1.33 with no rule, 4.83 with the rule loaded and 2.67 routed. On Opus 5.5 the routed score was 1.00.
- Knowledge-persistence scored 2.33 with no rule, 4.87 loaded and 2.60 routed.
- Limits: One judge, baseline noise 0.35. Routed scores are a best case because the harness offered only the target skill. Later work on 2026-11-24 and 2026-11-25 widened skill triggers and cut six rules. Five stayed.
- State on main at 1be533c496 (2026-11-26): superseded. PR 7541 kept 11 path rules because routing to their skills lost capability. Six rules were cut after trigger widening and five were kept (`evals/reports/rule-activation-trigger-widening-2026-11-24.md:3`).

## Decision

Do not fold an always-on rule into a skill without a routed-arm eval. Pass only when the routed positive score is within 0.35 of the loaded rule and the routed negative scenarios score no worse, the two-part gate in `evals/reports/rule-activation-trigger-widening-2026-11-24.md:27-29`.

## Related

- `.serena/memories/decision-skill-description-context-cost.md`
- `.serena/memories/memory/passive-context-vs-skills-vercel-research.md`
