# Gate latency: pre-push (markdown)

- Commit: `c5fc0f5becf8d80666302d1c0708bbdec36fee6b`
- Captured at: `2026-10-23T23:12:32.714671+00:00`
- Repetitions: 20
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 4.89, 5.71, 8.11 (1/5/15 min); 0.10 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class markdown --repetitions 20 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/perf/6734-measure-after c5fc0f5becf8d80666302d1c0708bbdec36fee6b refs/heads/perf/6734-measure-after f1f2a4d44837cdafd8245d02403c5113a448c5c1 --json ../perf-6734-after-out/pre-push-markdown.json --markdown ../perf-6734-after-out/pre-push-markdown.md
```

## Change class

- `markdown`: `README.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 20 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 20 | 135.734 | 149.949 | 133.930 | 153.763 |
| additions-advisory | job | 20 | 0.250 | 0.280 | 0.220 | 0.280 |
| bot-cascade-advisory | job | 20 | 0.680 | 0.760 | 0.610 | 0.760 |
| branch-config-prune-report | job | 20 | 0.220 | 0.230 | 0.210 | 0.240 |
| branch-context-policy | job | 20 | 0.260 | 0.280 | 0.240 | 0.280 |
| count-ratchets | job | 20 | 28.600 | 31.440 | 28.220 | 31.590 |
| dash-prohibition | job | 20 | 1.120 | 1.350 | 1.020 | 1.390 |
| group (4) | group total (sum) | 20 | 1.190 | 1.330 | 1.150 | 1.390 |
| group (5) | group total (sum) | 20 | 50.900 | 55.950 | 50.270 | 57.020 |
| group (7) | group total (sum) | 20 | 150.410 | 260.730 | 148.210 | 274.540 |
| mutation-safety | job | 20 | 0.090 | 0.100 | 0.090 | 0.100 |
| path-normalization | job | 20 | 3.330 | 3.720 | 3.280 | 3.790 |
| placeholder-identity | job | 20 | 0.310 | 0.320 | 0.300 | 0.330 |
| planning-artifacts | job | 20 | 0.090 | 0.110 | 0.070 | 0.120 |
| pre-pr-validation | job | 20 | 104.610 | 113.810 | 103.160 | 119.640 |
| push-ref-policy | job | 20 | 0.650 | 0.800 | 0.620 | 0.860 |
| push-ref-staleness | job | 20 | 0.400 | 0.710 | 0.350 | 0.850 |
| python-tests | job | 20 | 6.920 | 106.570 | 6.390 | 116.900 |
| python-unreachable-statements | job | 20 | 17.310 | 19.220 | 17.030 | 19.820 |
| repair-packed-refs | job | 20 | 0.070 | 0.080 | 0.070 | 0.090 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.080 |
| review-axis-drift | job | 20 | 0.130 | 0.150 | 0.110 | 0.160 |
| security-scan | job | 20 | 0.550 | 0.590 | 0.550 | 0.600 |
| security-suppression-policy | job | 20 | 0.230 | 0.240 | 0.220 | 0.250 |
| worktree-gc-report | job | 20 | 0.720 | 1.390 | 0.660 | 1.540 |
| zero-collection-tests | job | 20 | 37.120 | 41.910 | 36.550 | 41.930 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 134.609 | 134.520 | 25 | False | 0 | 3.95 | 3.37 |
| 1 | 0 | complete | 133.930 | 133.830 | 25 | False | 0 | 3.37 | 3.79 |
| 2 | 0 | complete | 134.348 | 134.250 | 25 | False | 0 | 3.79 | 3.33 |
| 3 | 0 | complete | 134.306 | 134.210 | 25 | False | 0 | 3.33 | 3.44 |
| 4 | 0 | complete | 135.734 | 135.640 | 25 | False | 0 | 3.44 | 6.38 |
| 5 | 0 | complete | 144.608 | 144.510 | 25 | False | 0 | 6.38 | 16.87 |
| 6 | 0 | complete | 143.859 | 143.750 | 25 | False | 0 | 16.87 | 20.11 |
| 7 | 0 | complete | 153.763 | 153.660 | 25 | False | 0 | 20.11 | 15.99 |
| 8 | 0 | complete | 147.765 | 147.670 | 25 | False | 0 | 15.99 | 19.09 |
| 9 | 0 | complete | 138.712 | 138.610 | 25 | False | 0 | 19.09 | 12.32 |
| 10 | 0 | complete | 149.949 | 149.840 | 25 | False | 0 | 12.32 | 17.12 |
| 11 | 0 | complete | 141.357 | 141.260 | 25 | False | 0 | 17.12 | 12.73 |
| 12 | 0 | complete | 137.825 | 137.710 | 25 | False | 0 | 12.73 | 7.05 |
| 13 | 0 | complete | 135.595 | 135.500 | 25 | False | 0 | 7.05 | 5.48 |
| 14 | 0 | complete | 136.085 | 135.990 | 25 | False | 0 | 5.48 | 4.91 |
| 15 | 0 | complete | 135.956 | 135.860 | 25 | False | 0 | 4.91 | 4.27 |
| 16 | 0 | complete | 135.014 | 134.920 | 25 | False | 0 | 4.27 | 4.36 |
| 17 | 0 | complete | 134.874 | 134.780 | 25 | False | 0 | 4.36 | 4.61 |
| 18 | 0 | complete | 134.973 | 134.880 | 25 | False | 0 | 4.61 | 3.76 |
| 19 | 0 | complete | 135.492 | 135.390 | 25 | False | 0 | 3.76 | 4.89 |

