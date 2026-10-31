# Gate latency: pre-push (workflows)

- Commit: `c5fc0f5becf8d80666302d1c0708bbdec36fee6b`
- Captured at: `2026-10-24T00:43:28.100940+00:00`
- Repetitions: 20
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 12.72, 11.88, 8.36 (1/5/15 min); 0.26 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class workflows --repetitions 20 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/perf/6734-measure-after c5fc0f5becf8d80666302d1c0708bbdec36fee6b refs/heads/perf/6734-measure-after f1f2a4d44837cdafd8245d02403c5113a448c5c1 --json ../perf-6734-after-out/pre-push-workflows.json --markdown ../perf-6734-after-out/pre-push-workflows.md
```

## Change class

- `workflows`: `.github/workflows/pytest.yml`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 20 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 20 | 134.690 | 139.996 | 134.163 | 143.435 |
| additions-advisory | job | 20 | 0.240 | 0.260 | 0.220 | 0.270 |
| bot-cascade-advisory | job | 20 | 0.680 | 0.730 | 0.610 | 0.790 |
| branch-config-prune-report | job | 20 | 0.230 | 0.240 | 0.200 | 0.250 |
| branch-context-policy | job | 20 | 0.240 | 0.270 | 0.230 | 0.280 |
| count-ratchets | job | 20 | 28.390 | 28.870 | 28.190 | 29.750 |
| dash-prohibition | job | 20 | 1.140 | 1.270 | 1.030 | 1.590 |
| group (4) | group total (sum) | 20 | 1.160 | 1.240 | 1.130 | 1.340 |
| group (5) | group total (sum) | 20 | 50.530 | 51.860 | 50.230 | 53.290 |
| group (7) | group total (sum) | 20 | 149.580 | 155.830 | 148.730 | 162.190 |
| mutation-safety | job | 20 | 0.090 | 0.090 | 0.090 | 0.090 |
| path-normalization | job | 20 | 3.320 | 3.500 | 3.280 | 3.620 |
| placeholder-identity | job | 20 | 0.310 | 0.310 | 0.300 | 0.310 |
| planning-artifacts | job | 20 | 0.090 | 0.100 | 0.070 | 0.100 |
| pre-pr-validation | job | 20 | 103.840 | 107.690 | 103.210 | 112.120 |
| push-ref-policy | job | 20 | 0.630 | 0.700 | 0.600 | 0.800 |
| push-ref-staleness | job | 20 | 0.390 | 0.440 | 0.350 | 0.740 |
| python-tests | job | 20 | 6.770 | 7.070 | 6.400 | 7.460 |
| python-unreachable-statements | job | 20 | 17.190 | 17.780 | 17.040 | 18.380 |
| repair-packed-refs | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| review-axis-drift | job | 20 | 0.130 | 0.150 | 0.120 | 0.150 |
| security-scan | job | 20 | 0.550 | 0.570 | 0.540 | 0.570 |
| security-suppression-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| workflow-local-run | job | 20 | 0.240 | 0.260 | 0.220 | 0.270 |
| worktree-gc-report | job | 20 | 0.680 | 0.730 | 0.610 | 0.760 |
| zero-collection-tests | job | 20 | 36.830 | 38.940 | 36.720 | 40.530 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 134.900 | 134.800 | 26 | False | 0 | 2.76 | 3.27 |
| 1 | 0 | complete | 135.276 | 135.180 | 26 | False | 0 | 3.27 | 5.98 |
| 2 | 0 | complete | 135.126 | 135.030 | 26 | False | 0 | 5.98 | 4.82 |
| 3 | 0 | complete | 138.659 | 138.560 | 26 | False | 0 | 4.82 | 9.49 |
| 4 | 0 | complete | 134.678 | 134.580 | 26 | False | 0 | 9.49 | 4.01 |
| 5 | 0 | complete | 134.690 | 134.600 | 26 | False | 0 | 4.01 | 3.54 |
| 6 | 0 | complete | 135.252 | 135.160 | 26 | False | 0 | 3.54 | 3.12 |
| 7 | 0 | complete | 135.628 | 135.530 | 26 | False | 0 | 3.12 | 7.17 |
| 8 | 0 | complete | 135.056 | 134.960 | 26 | False | 0 | 7.17 | 4.07 |
| 9 | 0 | complete | 134.522 | 134.430 | 26 | False | 0 | 4.07 | 3.73 |
| 10 | 0 | complete | 134.698 | 134.600 | 26 | False | 0 | 3.73 | 3.68 |
| 11 | 0 | complete | 134.438 | 134.340 | 26 | False | 0 | 3.68 | 3.30 |
| 12 | 0 | complete | 134.602 | 134.510 | 26 | False | 0 | 3.30 | 3.25 |
| 13 | 0 | complete | 134.175 | 134.080 | 26 | False | 0 | 3.25 | 3.65 |
| 14 | 0 | complete | 134.329 | 134.230 | 26 | False | 0 | 3.65 | 3.17 |
| 15 | 0 | complete | 134.443 | 134.350 | 26 | False | 0 | 3.17 | 3.43 |
| 16 | 0 | complete | 134.593 | 134.500 | 26 | False | 0 | 3.43 | 3.78 |
| 17 | 0 | complete | 134.163 | 134.070 | 26 | False | 0 | 3.78 | 5.18 |
| 18 | 0 | complete | 143.435 | 143.340 | 26 | False | 0 | 5.18 | 15.77 |
| 19 | 0 | complete | 139.996 | 139.900 | 26 | False | 0 | 15.77 | 12.72 |

