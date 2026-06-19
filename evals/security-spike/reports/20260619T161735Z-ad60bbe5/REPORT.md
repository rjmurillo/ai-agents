# Eval Report: 20260619T161735Z-ad60bbe5

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `1721245a74217e97...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `cffb1c29c1e51a12...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 82.4% |
| Baseline recall | 41.2% |
| Signed delta (agent - baseline) | +41.18pp |
| 95% bootstrap CI | [+15.79pp, +68.75pp] |
| Recall with errors | 82.4% |
| Recall excluding errors | 82.4% |
| Error count | 0 |
| Flakiness | true |

## Form-Factor Comparison

| Metric | Value |
|---|---|
| Agent recall | 82.4% |
| Skill recall | 84.3% |
| Skill - baseline delta | +43.14pp |
| Agent - skill delta | -1.96pp |
| Agent - skill 95% bootstrap CI | [-26.67pp, +26.67pp] |
| Agent tokens | 362804 |
| Skill tokens | 123853 |
| Verdict | `prefer-skill-form` |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 1.00,0.50,1.00 | 0.00,0.00,0.00 |
| F002 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F003 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |
| F004 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F005 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F006 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F008 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F009 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F010 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F011 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F012 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F013 | 0.00,1.00,0.00 | 0.00,0.00,0.00 |
| F014 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F015 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F016 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+15.79pp, +68.75pp]**. The interval **excludes** zero, so the observed delta is statistically distinguishable from no effect.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 482,808
- Total tokens out: 18,838
- Estimated cost: $1.7310 USD (rate as of 2026-05-03)
- Wall-clock time: 666.4s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F001, F013
