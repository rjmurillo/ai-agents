# Longitudinal pilot results, 2026-10-30

Source data: `report.json` and `records.jsonl` in this directory. Both hold hashes, counts, and scores only. No transcript or answer text is stored.

## Headline

No gain. Vendor-only and vendor plus local context tied on every measure. Both reached 12 of 15 cells accepted (0.80), mean F1 0.9867, 6 of 6 durable pairs accepted. The stale-context case passed. The tasks were too easy to separate the conditions (ceiling effect).

## Configuration

| Field | Value |
|---|---|
| Model | claude-haiku-5-5 |
| Harness | claude-cli 2.1.314 (Claude Code), print mode, one fresh session per task |
| Template revision | 14b6678972445139e2a2de3537691e5541191cce (skill-bootstrap template last commit) |
| Local-context revision | lc-1+114f5a8db9c0 |
| Pilot revision | pilot-1 (5 tasks, 3 repetitions, 2 conditions, 30 calls) |
| Observation window | 2026-10-31T05:06:00Z to 05:14:52Z (532.4 s) |
| Ceiling | $5.00 set; $0.2995 spent; not hit; run complete |

## Results

| Measure | vendor_only (baseline) | local_context |
|---|---|---|
| Cells accepted (F1 = 1.0) | 12 / 15 | 12 / 15 |
| Mean F1 | 0.9867 | 0.9867 |
| Durable pairs accepted | 6 / 6 | 6 / 6 |
| Repeated clarification requests | 0 | 0 |
| Human active correction minutes | unknown (none timed) | unknown (none timed) |
| Human decision points (fixture-declared) | 6 | 6 |
| Residual defects | 0 missing, 3 extra | 0 missing, 3 extra |
| Active model time | 253.8 s | 278.6 s |
| Retrieval tokens (estimate) | 0 | 954 |

All 3 unaccepted cells per condition are T1-seed, each with one extra path (F1 0.9333). Every other task scored 1.0 in both conditions.

## Cost split (USD)

| Component | vendor_only | local_context |
|---|---|---|
| Bootstrap | 0.00 (none built) | unknown (building the context was not measured) |
| Execution (accepted cells) | 0.1258 | 0.1155 |
| Retrieval | unknown (not separable in one call) | unknown |
| Maintenance | 0.00 model spend (deterministic probes) | 0.00 model spend |
| Rework (non-accepted cells) | 0.0263 | 0.0319 |
| Total | unknown | unknown |

Known parts sum to 0.1521 (vendor_only) and 0.1474 (local_context). That difference is noise at this size. Total spend including both conditions was $0.2995.

## Specific checks

- Retained correction (C1, approved after T2, used in T3): no gain. T3 scored 1.0 in both conditions, so the correction could not help.
- Stale-context case (F1 invalidated by the rename before T4): detected. The fact was withheld and flagged in all 3 repetitions. No false alarm, no silent reuse.
- Elapsed time: 532.4 s total, equal to summed active model time within rounding. Waiting time was not separately measurable, so it is reported as null, not 0.
- Held-out follow-up (T5): 1.0 in both conditions.

## Limitations

- One repository, one model, five grep-sized tasks. Results are fixture results and do not generalize to customer outcomes.
- Ceiling effect: the baseline already scores near 1.0, so this run cannot show a benefit. A harder sequence is needed to test the claim.
- The correction text is scripted, not produced by a human review. Human minutes were not timed.
- Bootstrap cost for building the local context was not measured. Retrieval cost is not separable.
- Clarification requests are counted as prose lines ending in a question mark.
- No production verifier or named review owner exists, so no production-value claim is made.
