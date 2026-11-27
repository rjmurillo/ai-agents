# A gate that errors on most of the corpus is itself the bug

**Atomicity**: 90%
**Category**: Guard calibration, golden principles
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E020. State checked on main at 1be533c496 (2026-11-26).

## Question

When a gate errors on most of the corpus, is the corpus wrong or the gate?

## Conventional answer

The golden-principles GP-003 gate and its remediation text said every skill must declare a model field.

## First-principles position

ADR-080 makes the model field optional. Counting the corpus showed that nearly every skill omits it by policy. The gate flagged the compliant skills and stayed quiet on the few that use the exception.

## Evidence with limits

- On 2026-07-30, 91 of 98 skills omitted the model field. The gate flagged those 91 skills, or 93 percent, for following policy.
- All 7 that set the field used `haiku`, the ADR-080 exception (2026-07-30).
- Limits: One count on 2026-07-30 at one checkout. The work for issue 4006 changed the gate.
- State on main at 1be533c496 (2026-11-26): fixed. `.agents/governance/golden-principles.md:38` says the model field is optional per ADR-080. Omitting it inherits the harness default.

## Decision

When a gate errors on most of the corpus, count the corpus against the governing ADR before editing files to satisfy it. Check that remediation text matches current policy.

## Related

- `.serena/memories/decision-calibrate-guards-on-the-whole-corpus.md`
- `.serena/memories/decision-validator-full-scan-corpus-asymmetry.md`
