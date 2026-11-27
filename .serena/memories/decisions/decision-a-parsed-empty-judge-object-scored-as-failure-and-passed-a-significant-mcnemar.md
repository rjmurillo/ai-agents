# Empty judge objects produced a misleading McNemar result and exit 0

**Atomicity**: 90%
**Category**: Eval design
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E164. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a parsed but empty judge response count as a scored failure?

## Conventional answer

The judge error handling was expected to exit 2 before scoring any failed response.

## First-principles position

The evaluator parsed `{}` and counted it as a real failure. Ten empty responses produced a McNemar p-value below 0.05 and exit 0. The test measured broken judge output rather than rule activation.

## Evidence with limits

- The synthetic probe returned exit 0, `judge_failed=False`, and 10 scored failures (2026-07-27).
- McNemar reported discordant counts of 10 and 0, with p = 0.0009765625 (2026-07-27).
- Explicit transport errors returned exit 2 in the same probe (2026-07-27).
- Limits: One branch probe on a synthetic degraded set. A search for `_judge_score_shape_error` under `tests/` did not find an empty-object test.
- State on main at 1be533c496 (2026-11-26): fixed. `scripts/eval/eval-rule-activation.py:1292` rejects missing, noninteger, or out-of-range scores. Line 721 clears the failure flag only after validation.

## Decision

Validate every required score field for type and range before scoring a parsed object. Test the empty object alongside explicit judge errors.

## Related

- `.serena/memories/eval/eval-held-out-gated-optimization.md`
