# Skill: A recent-N completed-runs sample censors slow workflows (92%)

**Atomicity Score**: 92%
**Source**: Retrospective `.agents/retrospective/2026-08-02-wrong-fix-before-search.md`
**Date**: 2026-08-02
**Validation Count**: 1 (measurement reversed, then re-reversed, before anything was filed)
**Tag**: helpful
**Impact**: 9/10 (the truncated sample supported the exact opposite conclusion)

## Statement

Sampling `gh run list --status completed` over the most-recent N runs structurally excludes
long-running workflows: slow runs are disproportionately still `in_progress` and never enter
the sample. Paginate to 500+ runs before drawing any conclusion about CI duration.

## Evidence

2026-08-02, measuring whether `strict_required_status_checks_policy: true` would gridlock
merges in `rjmurillo/ai-agents`.

| Sample | Critical path p50 | Merges landed per CI run | Conclusion |
|---|---|---|---|
| 100 runs, 1 page, `status=completed` | 2.6 min | 0.19 | Strict checks VIABLE |
| 500 runs, 5 pages | 13.5 min (`Python Tests`) | 1.02 at p50, 1.40 at p95 | Strict checks GRIDLOCK |

A 5x understatement of the critical path, and a conclusion that flipped. The first sample never
contained `Python Tests` (13.5 min) or `AI PR Quality Gate` (12.3 min) at all, the only two
workflows that matter, because on a busy repo those two are almost always still running when
the most recent 100 completed runs are drawn.

## Mechanism

This is **censoring bias**, not selection bias. The filter is on completion state, which is
correlated with the very variable being measured. Every slow run is systematically truncated
out of the window while every fast run survives it. The sample is not merely small; it is
biased in a known direction, so widening it moves the estimate one way only.

## Guard

- Paginate. `--limit 500` and confirm the page count actually returned.
- Check whether the workflows you care about appear in the sample by name before computing any
  statistic. If a named workflow is absent, the sample is censored, not the workflow idle.
- Report which workflows are in the sample alongside the percentile, so a reader can spot the
  omission.

## Related

- `.serena/memories/decision-calibrate-guards-on-the-whole-corpus.md` covers **self-selection**
  bias (the corpus you sample chose itself). This memory covers **censoring** (the filter
  correlates with the measured variable). Mechanically distinct; both produce a confidently
  wrong number from a real query.
