# Eval Report: 20260528T061958Z-d7d69065

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `6e919c6009c0efda...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `927d542a5715836a...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 54.2% |
| Baseline recall | 62.5% |
| Signed delta (agent - baseline) | -8.33pp |
| 95% bootstrap CI | [-41.67pp, +18.75pp] |
| Recall with errors | 54.2% |
| Recall excluding errors | 54.2% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| V001 | 0.00,0.00,0.50 | 0.00,0.00,0.50 |
| V002 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| V003 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| V004 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| V005 | 0.00,0.00,0.00 | 1.00,1.00,1.00 |
| V006 | 0.50,1.00,0.50 | 0.50,0.50,0.50 |
| V007 | 0.50,0.50,0.50 | 0.50,0.50,0.00 |
| V008 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: this run halted at AC-10's flakiness gate. The CI below is reported for diagnostic context; statistical significance does not unblock the verdict, which is fixed at `halt-due-to-flakiness` until the variance source is investigated and the methodology is re-run.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-41.67pp, +18.75pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

**Verdict**: `halt-due-to-flakiness`

## Cost and Resource Summary

- Total tokens in: 51,546
- Total tokens out: 5,628
- Estimated cost: $0.2391 USD (rate as of 2026-05-03)
- Wall-clock time: 190.4s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: _(none excluded)_
