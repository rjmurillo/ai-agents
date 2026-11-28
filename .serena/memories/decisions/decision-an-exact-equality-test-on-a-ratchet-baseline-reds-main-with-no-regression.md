# A ratchet equality test can fail main without a regression

**Atomicity**: 90%
**Category**: CI ratchets
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E101. State checked on main at 1be533c496 (2026-11-26).

## Question

Should a scalar count ratchet require the measured count to equal its baseline exactly?

## Conventional answer

Exact equality between the measured count and the baseline was considered the safer guard.

## First-principles position

The outage review found that each failed check measured a count above its baseline. It also found passing checks where the count sat below the baseline by an allowed margin. An equality test would fail those checks without a regression.

## Evidence with limits

- The 2026-08-05 review found six outages above baseline: type-ignore 56 > 55, taste 609 > 608, 602 > 601, 596 > 595, Ruff 140 > 126, and CLI exit 33 > 14.
- Live ratchets showed memory-index at 424 vs 425 and taste at 582 vs 583 (2026-08-04 to 2026-08-05). The baseline health check permitted a margin of 1 at the time.
- Limits: One model reconstructed the outage table from PR history without replaying it end to end. The margin observations covered only a few ratchets. PR 4515 records a stale-high case (592 vs 591, reviewed 2026-08-05).
- State on main at 1be533c496 (2026-11-26): superseded. `scripts/ci/count_ratchet.py:385` sets `MAX_BASELINE_SLACK = 6`. PR 4515 removed the equality test that had failed main.

## Decision

Allow a bounded margin below the baseline, as `count_ratchet.py` does with `MAX_BASELINE_SLACK`. Treat a count above baseline as a regression.

## Related

- `.serena/memories/decision-every-merge-invalidates-every-open-pr.md`
- `.serena/memories/ci/ci-count-ratchets-require-branch-freshness.md`
