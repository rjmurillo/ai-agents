# Eval Report: 20260528T055934Z-5f4d8ad4

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `372c90434fc8a745...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `26136df314d6c7b5...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 56.2% |
| Baseline recall | 66.7% |
| Signed delta (agent - baseline) | -10.42pp |
| 95% bootstrap CI | [-33.33pp, +14.58pp] |
| Recall with errors | 56.2% |
| Recall excluding errors | 56.2% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| A001 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| A002 | 0.50,0.50,0.50 | 0.50,0.00,0.50 |
| A003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| A004 | 0.00,0.50,0.00 | 0.50,0.50,0.50 |
| A005 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| A006 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| A007 | 0.50,0.50,1.00 | 0.50,0.50,0.50 |
| A008 | 0.00,0.00,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: this run halted at AC-10's flakiness gate. The CI below is reported for diagnostic context; statistical significance does not unblock the verdict, which is fixed at `halt-due-to-flakiness` until the variance source is investigated and the methodology is re-run.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-33.33pp, +14.58pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

**Verdict**: `halt-due-to-flakiness`

## Cost and Resource Summary

- Total tokens in: 185,580
- Total tokens out: 7,563
- Estimated cost: $0.6702 USD (rate as of 2026-05-03)
- Wall-clock time: 253.5s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: _(none excluded)_
