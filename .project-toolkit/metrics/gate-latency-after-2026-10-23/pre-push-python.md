# Gate latency: pre-push (python)

- Commit: `c5fc0f5becf8d80666302d1c0708bbdec36fee6b`
- Captured at: `2026-10-23T23:57:53.216437+00:00`
- Repetitions: 20
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 3.26, 4.87, 5.44 (1/5/15 min); 0.07 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class python --repetitions 20 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/perf/6734-measure-after c5fc0f5becf8d80666302d1c0708bbdec36fee6b refs/heads/perf/6734-measure-after f1f2a4d44837cdafd8245d02403c5113a448c5c1 --json ../perf-6734-after-out/pre-push-python.json --markdown ../perf-6734-after-out/pre-push-python.md
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 20 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 20 | 134.877 | 135.761 | 133.761 | 135.950 |
| additions-advisory | job | 20 | 0.250 | 0.270 | 0.240 | 0.270 |
| bot-cascade-advisory | job | 20 | 0.680 | 0.730 | 0.580 | 0.790 |
| branch-config-prune-report | job | 20 | 0.220 | 0.250 | 0.200 | 0.250 |
| branch-context-policy | job | 20 | 0.240 | 0.270 | 0.230 | 0.270 |
| count-ratchets | job | 20 | 28.410 | 28.750 | 28.080 | 28.840 |
| dash-prohibition | job | 20 | 1.130 | 1.220 | 0.980 | 1.590 |
| group (4) | group total (sum) | 20 | 1.170 | 1.230 | 1.140 | 1.250 |
| group (5) | group total (sum) | 20 | 50.550 | 51.150 | 49.970 | 51.150 |
| group (7) | group total (sum) | 20 | 149.760 | 151.000 | 148.930 | 151.010 |
| mutation-safety | job | 20 | 0.090 | 0.090 | 0.090 | 0.090 |
| path-normalization | job | 20 | 3.330 | 3.390 | 3.280 | 3.750 |
| placeholder-identity | job | 20 | 0.310 | 0.310 | 0.300 | 0.310 |
| planning-artifacts | job | 20 | 0.090 | 0.110 | 0.070 | 0.110 |
| pre-pr-validation | job | 20 | 103.900 | 104.700 | 103.270 | 104.990 |
| push-ref-policy | job | 20 | 0.630 | 0.700 | 0.600 | 0.720 |
| push-ref-staleness | job | 20 | 0.410 | 0.480 | 0.360 | 0.620 |
| python-lint-advisory | job | 20 | 0.180 | 0.190 | 0.110 | 0.190 |
| python-tests | job | 20 | 6.740 | 7.110 | 6.330 | 7.170 |
| python-type-check | job | 20 | 0.250 | 0.280 | 0.220 | 0.280 |
| python-unreachable-statements | job | 20 | 17.180 | 17.560 | 16.990 | 17.600 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.080 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| review-axis-drift | job | 20 | 0.130 | 0.150 | 0.110 | 0.150 |
| security-scan | job | 20 | 0.550 | 0.560 | 0.540 | 0.560 |
| security-suppression-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| worktree-gc-report | job | 20 | 0.680 | 0.750 | 0.600 | 0.760 |
| zero-collection-tests | job | 20 | 36.850 | 37.040 | 36.600 | 37.270 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 135.295 | 135.200 | 27 | False | 0 | 4.61 | 5.11 |
| 1 | 0 | complete | 135.158 | 135.060 | 27 | False | 0 | 5.11 | 5.09 |
| 2 | 0 | complete | 135.950 | 135.850 | 27 | False | 0 | 5.09 | 4.83 |
| 3 | 0 | complete | 135.118 | 135.020 | 27 | False | 0 | 4.83 | 5.41 |
| 4 | 0 | complete | 135.749 | 135.650 | 27 | False | 0 | 5.41 | 5.13 |
| 5 | 0 | complete | 135.589 | 135.490 | 27 | False | 0 | 5.13 | 4.18 |
| 6 | 0 | complete | 135.133 | 135.040 | 27 | False | 0 | 4.18 | 3.76 |
| 7 | 0 | complete | 134.909 | 134.820 | 27 | False | 0 | 3.76 | 4.04 |
| 8 | 0 | complete | 135.761 | 135.670 | 27 | False | 0 | 4.04 | 3.87 |
| 9 | 0 | complete | 134.598 | 134.500 | 27 | False | 0 | 3.87 | 4.65 |
| 10 | 0 | complete | 134.274 | 134.180 | 27 | False | 0 | 4.65 | 3.76 |
| 11 | 0 | complete | 134.877 | 134.780 | 27 | False | 0 | 3.76 | 3.88 |
| 12 | 0 | complete | 134.311 | 134.220 | 27 | False | 0 | 3.88 | 3.13 |
| 13 | 0 | complete | 134.342 | 134.250 | 27 | False | 0 | 3.13 | 4.19 |
| 14 | 0 | complete | 133.761 | 133.670 | 27 | False | 0 | 4.19 | 4.07 |
| 15 | 0 | complete | 134.785 | 134.690 | 27 | False | 0 | 4.07 | 3.59 |
| 16 | 0 | complete | 135.202 | 135.110 | 27 | False | 0 | 3.59 | 4.70 |
| 17 | 0 | complete | 134.811 | 134.720 | 27 | False | 0 | 4.70 | 4.39 |
| 18 | 0 | complete | 134.416 | 134.320 | 27 | False | 0 | 4.39 | 3.41 |
| 19 | 0 | complete | 134.256 | 134.160 | 27 | False | 0 | 3.41 | 3.26 |

