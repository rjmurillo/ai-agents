# Rules loaded every turn raised eval scores, but shortening universal.md lowered them

**Atomicity**: 90%
**Category**: Rule eval, instruction context
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E072. State checked on main at 1be533c496 (2026-11-26).

## Question

Do always-on rules lift behavior, and does compressing them keep the lift?

## Conventional answer

The Vercel post, cited in context-optimizer, says a compact docs index that is always loaded beats skills. Shrinking 40 KB to 8 KB kept 100%.

## First-principles position

On rule scenarios, the full rules beat no rule by a measurable margin. A micro core for universal.md lost score on both Sonnet and Opus. The same micro core did not hurt voice or builder-ethos. Compression is mixed, not uniformly harmful. Only universal.md fell below the floor with p < 0.05. Each rule needs its own test before shrinking.

## Evidence with limits

- At HEAD 902278fa50 (2026-11-26) the full rules beat no rule on 49 positive pairs by +0.34 (sign-flip p = 0.0055, 24 wins, 21 ties, 4 losses).
- A micro core for universal.md scored -0.36 on Sonnet and -0.59 on Opus (p = 0.025). It failed the floor on S1, S4 and R2.
- The same micro core scored +0.20 and +0.12 on voice, and about even on builder-ethos.
- A shortened voice rule lost 0.39 (p = 0.078, n = 12), which is not statistically meaningful.
- Quote: "HEAD full-vs-baseline (no rule) on positive scenarios, both HEAD runs pooled, truncated cells excluded: +0.34, n=49, sign-flip p=0.0055, 24 win/21 tie/4 loss."
- Limits: Scenarios were written to probe these rules, so plain-turn lift may differ in real traffic. Only universal.md was statistically meaningful. The 0.39 loss was not. The model behind the pooled +0.34 was not confirmed in the lines read. Single session on 2026-11-26.
- State on main at 1be533c496 (2026-11-26): no repo artifact. The pooled +0.34 lift and the micro-core results are not recorded on main.

## Decision

Keep universal.md at full text. Do not claim terse compression always hurts, since voice improved under the micro core. Test each rule before shrinking it.

## Related

- `.serena/memories/instruction-context-efficiency-not-quality.md`
- `.serena/memories/memory/passive-context-vs-skills-vercel-research.md`
