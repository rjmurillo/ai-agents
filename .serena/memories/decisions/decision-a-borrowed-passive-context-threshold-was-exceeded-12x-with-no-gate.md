# Vercel tested knowledge the model lacked, so its result does not justify loading behavioral rules every turn

**Atomicity**: 90%
**Category**: Instruction context
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E059. State checked on main at 1be533c496 (2026-11-26).

## Question

Does the Vercel passive-context result justify putting behavioral rules in always-on context?

## Conventional answer

Passive context scored 100% against 53 to 79% for skills in the Vercel result. The context-optimizer advice was to put knowledge in always-on context.

## First-principles position

Vercel tested Next.js 16 APIs absent from model training data. This repo applied the result to familiar behavioral rules. The study did not test those rules. By 2026-07-30, the measured Python context was about 12 times the cited 8KB threshold. That threshold did not bind the repo's budget gate.

## Evidence with limits

- Vercel's suite targeted APIs chosen because they were absent from training data.
- An earlier PR (PR 1022) wrote that about 4.5KB of passive context was under the 8KB threshold. The corpus measured about 95KB on 2026-07-30.
- The `instruction_budget.py` gate reported 94,741 bytes over 11 files for a .py edit, which is 95.7% of a 99,000-byte ceiling (2026-07-30). The ceiling ratchets to measured size.
- Limits: Source reading plus one gate run on 2026-07-30. The 94,741 figure is the per-language always-on baseline, not a single file set. It does not show the rules hurt. Sweep id E072 data shows the opposite for the voice, builder-ethos and universal rules.
- State on main at 1be533c496 (2026-11-26): fixed. `src/claude/skills/context-optimizer/SKILL.md:114` says the Vercel result is real and narrow, and that its suite targeted APIs absent from model training data.

## Decision

Do not cite the Vercel 100% against 79% result to justify always-on behavioral rules. Cite it only for knowledge the model lacks. The existing memory page lists HIGH confidence with no scope note and should link here.

## Related

- `.serena/memories/memory/passive-context-vs-skills-vercel-research.md`
- `.serena/memories/instruction-context-efficiency-not-quality.md`
- `.serena/memories/validation/instruction-budget-always-on-headroom.md`
- `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`
