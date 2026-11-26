# Eval Report: 20261126T051545Z-9db16cc0

- Model: `claude-sonnet-5-5`
- Agent prompt SHA: `dfcb7790a0e87714...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `f6310eb016cba794...`
- Fixture inventory: 8
- System fingerprints: `claude-sonnet-5-5`
- Credential step: gateway: the host at ANTHROPIC_BASE_URL decides the account and the bill
- Seed: `0`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 58.3% |
| Baseline recall | 72.9% |
| Signed delta (agent - baseline) | -14.58pp |
| 95% bootstrap CI | [-29.17pp, -2.08pp] |
| Recall with errors | 58.3% |
| Recall excluding errors | 58.3% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| A001 | 0.50,0.00,0.50 | 0.50,0.50,0.50 |
| A002 | 0.00,0.00,0.00 | 0.00,0.00,0.50 |
| A003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| A004 | 0.50,1.00,1.00 | 1.00,1.00,1.00 |
| A005 | 1.00,1.00,1.00 | 1.00,1.00,0.50 |
| A006 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| A007 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| A008 | 0.50,0.50,0.50 | 1.00,0.50,1.00 |

## Confidence Interval

**Note**: this run halted at AC-10's flakiness gate. The CI below is reported for diagnostic context; statistical significance does not unblock the verdict, which is fixed at `halt-due-to-flakiness` until the variance source is investigated and the methodology is re-run.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-29.17pp, -2.08pp]**. The interval **excludes** zero, so the observed delta is statistically distinguishable from no effect.

## Recommendation

**Verdict**: `halt-due-to-flakiness`

## Cost and Resource Summary

- Total tokens in: 159,012
- Total tokens out: 5,334
- Estimated cost: metered as requests, not billed per token (no public per-token rate for this provider)
- Wall-clock time: 244.9s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: _(none excluded)_
