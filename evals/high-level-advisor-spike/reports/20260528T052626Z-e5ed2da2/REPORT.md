# Eval Report: 20260528T052626Z-e5ed2da2

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `9ce1bd6f1359a572...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `7839280be7b1ea98...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 58.3% |
| Baseline recall | 47.9% |
| Signed delta (agent - baseline) | +10.42pp |
| 95% bootstrap CI | [-2.08pp, +25.00pp] |
| Recall with errors | 58.3% |
| Recall excluding errors | 58.3% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| H001 | 1.00,1.00,0.50 | 0.00,0.50,0.50 |
| H002 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| H003 | 1.00,0.50,0.50 | 0.50,0.50,0.00 |
| H004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| H005 | 0.50,0.50,0.50 | 1.00,0.50,0.50 |
| H006 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| H007 | 0.00,0.00,0.50 | 0.00,0.00,0.00 |
| H008 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: this run halted at AC-10's flakiness gate. The CI below is reported for diagnostic context; statistical significance does not unblock the verdict, which is fixed at `halt-due-to-flakiness` until the variance source is investigated and the methodology is re-run.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-2.08pp, +25.00pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

**Verdict**: `halt-due-to-flakiness`

## Cost and Resource Summary

- Total tokens in: 49,716
- Total tokens out: 5,833
- Estimated cost: $0.2366 USD (rate as of 2026-05-03)
- Wall-clock time: 204.2s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: _(none excluded)_
