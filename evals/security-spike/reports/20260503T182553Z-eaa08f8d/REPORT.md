# Eval Report: 20260503T182553Z-eaa08f8d

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `c90b17a396de54a5...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `9d77ba35e2acf78f...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 78.6% |
| Baseline recall | 40.5% |
| Signed delta (agent - baseline) | +38.10pp |
| 95% bootstrap CI | [+11.11pp, +64.29pp] |
| Recall with errors | 78.6% |
| Recall excluding errors | 78.6% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 1.00,0.50,0.50 | 0.00,0.00,0.00 |
| F002 | 0.50,1.00,0.00 | 0.50,0.50,0.50 |
| F003 | 0.50,0.50,0.00 | 0.00,0.00,0.00 |
| F004 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F005 | 1.00,1.00,1.00 | 1.00,1.00,0.00 |
| F006 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F008 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F009 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F010 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |

## Confidence Interval

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+11.11pp, +64.29pp]**. The interval **excludes** zero, so the observed delta is statistically distinguishable from no effect.

## Recommendation

**Verdict**: `halt-due-to-flakiness`

## Cost and Resource Summary

- Total tokens in: 253,266
- Total tokens out: 8,574
- Estimated cost: $0.8884 USD (rate as of 2026-05-03)
- Wall-clock time: 620.0s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: _(none excluded)_
