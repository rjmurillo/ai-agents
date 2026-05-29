# Eval Report: 20260528T060742Z-a76d72b8

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `3aad35c74ecde56a...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `da2da247a5573745...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 45.8% |
| Baseline recall | 41.7% |
| Signed delta (agent - baseline) | +4.17pp |
| 95% bootstrap CI | [-29.17pp, +35.42pp] |
| Recall with errors | 45.8% |
| Recall excluding errors | 45.8% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| Q001 | 0.00,0.00,0.50 | 0.50,0.00,0.00 |
| Q002 | 1.00,1.00,1.00 | 0.00,0.00,0.50 |
| Q003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| Q004 | 0.50,0.50,0.50 | 0.50,0.50,0.00 |
| Q005 | 0.00,0.00,0.50 | 1.00,1.00,1.00 |
| Q006 | 0.50,0.00,0.50 | 0.50,0.50,0.50 |
| Q007 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| Q008 | 0.00,0.00,0.00 | 0.00,0.00,0.50 |

## Confidence Interval

**Note**: this run halted at AC-10's flakiness gate. The CI below is reported for diagnostic context; statistical significance does not unblock the verdict, which is fixed at `halt-due-to-flakiness` until the variance source is investigated and the methodology is re-run.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-29.17pp, +35.42pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

**Verdict**: `halt-due-to-flakiness`

## Cost and Resource Summary

- Total tokens in: 168,048
- Total tokens out: 5,909
- Estimated cost: $0.5928 USD (rate as of 2026-05-03)
- Wall-clock time: 203.8s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: _(none excluded)_
