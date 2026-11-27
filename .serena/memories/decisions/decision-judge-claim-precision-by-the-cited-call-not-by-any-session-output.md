# A claim checker scored 0.70 precision by the cited call and 0.925 by any session output

**Atomicity**: 90%
**Category**: Claim checking, proof standards
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E029. State checked on main at 1be533c496 (2026-11-26).

## Question

How should a claim checker's precision be scored, by the cited call or by any session output?

## Conventional answer

Whole session claim checking suggested the detector precision gate passed. Zero false CAP looked like good evidence.

## First-principles position

Scoring against any session output let unrelated output vouch for a claim. Scoring against the cited call is the real standard. The first draft verdict to proceed had checked the wrong thing.

## Evidence with limits

- A spike on the Receipts NO CAP detector (2026-11-24): 28 of 40 = 0.70 judged by the cited call, versus 37 of 40 = 0.925 judged by any output.
- 12 of 40 NO CAP items were unsupported. 9 of the 12 wrong citations are SHA stamps. Strict precision of 0.70 is below the 0.85 threshold.
- 0 CAP in 146 stamps missed the real "19 pass" versus 18.
- Limits: One spike, 40 labeled items, 146 stamps. Labels were made by the same agent that wrote the checker. A third party tool was evaluated and not shipped. The work is on a branch only.
- State on main at 1be533c496 (2026-11-26): no repo artifact. A search found only unrelated "no capability" hits on main. The spike commits sit on a spike branch. Nothing in the repo states the precision.

## Decision

State the proof standard before scoring a claim checker. Score precision against the cited call, and count only tool output, never the agent's own text.

## Related

- `.serena/memories/decision-calibrate-guards-on-the-whole-corpus.md`
