# Gate latency: pre-push (python)

- Commit: `0e98cb2d125635c1a7f71c7a89f70df0293a94ff`
- Captured at: `2026-10-24T01:07:12.771634+00:00`
- Repetitions: 3
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 3.45, 4.50, 5.74 (1/5/15 min); 0.07 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class python --repetitions 3 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/perf/6734-measure-after 0e98cb2d125635c1a7f71c7a89f70df0293a94ff refs/heads/perf/6734-measure-after 7d4ef439fae19671cbc3733ddca2312f0b4d61c9 --json ../perf-6734-after-out/control-oldsha-coldtestmon.json --markdown ../perf-6734-after-out/control-oldsha-coldtestmon.md
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=3 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 3 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 3 | 264.807 | 263.720 | 262.708 |
| additions-advisory | job | 3 | 0.270 | 0.270 | 0.250 |
| bot-cascade-advisory | job | 3 | 0.280 | 0.280 | 0.270 |
| branch-config-prune-report | job | 3 | 0.230 | 0.220 | 0.220 |
| branch-context-policy | job | 3 | 0.260 | 0.250 | 0.230 |
| count-ratchets | job | 3 | 40.330 | 40.270 | 39.950 |
| dash-prohibition | job | 3 | 0.300 | 0.290 | 0.280 |
| group (4) | group total (sum) | 3 | 1.220 | 1.210 | 1.160 |
| group (5) | group total (sum) | 3 | 61.660 | 61.580 | 61.060 |
| group (7) | group total (sum) | 3 | 313.600 | 312.610 | 310.190 |
| mutation-safety | job | 3 | 0.100 | 0.090 | 0.090 |
| path-normalization | job | 3 | 3.370 | 3.320 | 3.310 |
| placeholder-identity | job | 3 | 0.320 | 0.310 | 0.310 |
| planning-artifacts | job | 3 | 0.110 | 0.110 | 0.080 |
| pre-pr-validation | job | 3 | 221.970 | 220.920 | 220.260 |
| push-ref-policy | job | 3 | 0.690 | 0.660 | 0.610 |
| push-ref-staleness | job | 3 | 0.510 | 0.400 | 0.390 |
| python-lint-advisory | job | 3 | 0.190 | 0.160 | 0.150 |
| python-tests | job | 3 | 52.690 | 52.370 | 51.280 |
| python-type-check | job | 3 | 0.270 | 0.240 | 0.230 |
| python-unreachable-statements | job | 3 | 17.290 | 17.110 | 17.030 |
| repair-packed-refs | job | 3 | 0.080 | 0.070 | 0.070 |
| repo-health | job | 3 | 0.070 | 0.070 | 0.070 |
| review-axis-drift | job | 3 | 0.160 | 0.140 | 0.120 |
| security-scan | job | 3 | 0.560 | 0.550 | 0.540 |
| security-suppression-policy | job | 3 | 0.230 | 0.230 | 0.230 |
| worktree-gc-report | job | 3 | 0.730 | 0.700 | 0.640 |
| zero-collection-tests | job | 3 | 38.060 | 37.070 | 36.190 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 262.708 | 262.610 | 27 | False | 0 | 2.49 | 7.08 |
| 1 | 0 | complete | 264.807 | 264.710 | 27 | False | 0 | 7.08 | 3.53 |
| 2 | 0 | complete | 263.720 | 263.620 | 27 | False | 0 | 3.53 | 3.45 |

