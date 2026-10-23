# Gate latency: pre-push (workflows)

- Commit: `0e98cb2d125635c1a7f71c7a89f70df0293a94ff`
- Captured at: `2026-10-23T09:22:12.425904+00:00`
- Repetitions: 20
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 2.80, 3.46, 3.67 (1/5/15 min); 0.06 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class workflows --repetitions 20 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/perf/6734-measure-scratch 0e98cb2d125635c1a7f71c7a89f70df0293a94ff refs/heads/perf/6734-measure-scratch 7d4ef439fae19671cbc3733ddca2312f0b4d61c9 --json ../perf-6734-out/pre-push-workflows.json --markdown ../perf-6734-out/pre-push-workflows.md
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
| __hook__ | hook wall clock | 20 | 263.034 | 267.077 | 261.980 | 270.878 |
| additions-advisory | job | 20 | 0.250 | 0.260 | 0.220 | 0.260 |
| bot-cascade-advisory | job | 20 | 0.720 | 0.850 | 0.630 | 1.570 |
| branch-config-prune-report | job | 20 | 0.220 | 0.240 | 0.210 | 0.240 |
| branch-context-policy | job | 20 | 0.250 | 0.260 | 0.230 | 0.260 |
| count-ratchets | job | 20 | 40.200 | 40.620 | 39.930 | 41.270 |
| dash-prohibition | job | 20 | 0.730 | 0.800 | 0.670 | 0.800 |
| group (4) | group total (sum) | 20 | 1.180 | 1.390 | 1.140 | 1.680 |
| group (5) | group total (sum) | 20 | 61.660 | 62.120 | 61.430 | 63.440 |
| group (7) | group total (sum) | 20 | 312.350 | 317.420 | 309.930 | 322.050 |
| mutation-safety | job | 20 | 0.090 | 0.090 | 0.090 | 0.090 |
| path-normalization | job | 20 | 3.300 | 3.350 | 3.270 | 3.350 |
| placeholder-identity | job | 20 | 0.300 | 0.310 | 0.300 | 0.310 |
| planning-artifacts | job | 20 | 0.090 | 0.110 | 0.070 | 0.110 |
| pre-pr-validation | job | 20 | 220.300 | 224.320 | 219.200 | 227.800 |
| push-ref-policy | job | 20 | 0.650 | 0.860 | 0.610 | 1.150 |
| push-ref-staleness | job | 20 | 0.420 | 0.480 | 0.370 | 0.620 |
| python-tests | job | 20 | 53.360 | 57.880 | 52.180 | 59.000 |
| python-unreachable-statements | job | 20 | 16.930 | 17.120 | 16.840 | 17.570 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| review-axis-drift | job | 20 | 0.130 | 0.150 | 0.110 | 0.150 |
| security-scan | job | 20 | 0.540 | 0.560 | 0.540 | 0.560 |
| security-suppression-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| workflow-local-run | job | 20 | 0.240 | 0.250 | 0.230 | 0.260 |
| worktree-gc-report | job | 20 | 0.620 | 0.920 | 0.570 | 1.030 |
| zero-collection-tests | job | 20 | 36.090 | 36.430 | 35.940 | 36.510 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 262.997 | 262.900 | 26 | False | 0 | 4.41 | 2.79 |
| 1 | 0 | complete | 261.995 | 261.900 | 26 | False | 0 | 2.79 | 2.85 |
| 2 | 0 | complete | 263.034 | 262.940 | 26 | False | 0 | 2.85 | 2.95 |
| 3 | 0 | complete | 262.591 | 262.500 | 26 | False | 0 | 2.95 | 3.28 |
| 4 | 0 | complete | 263.348 | 263.260 | 26 | False | 0 | 3.28 | 2.66 |
| 5 | 0 | complete | 266.697 | 266.600 | 26 | False | 0 | 2.66 | 3.34 |
| 6 | 0 | complete | 267.077 | 266.980 | 26 | False | 0 | 3.34 | 4.20 |
| 7 | 0 | complete | 263.031 | 262.940 | 26 | False | 0 | 4.20 | 2.85 |
| 8 | 0 | complete | 263.117 | 263.020 | 26 | False | 0 | 2.85 | 3.40 |
| 9 | 0 | complete | 262.709 | 262.610 | 26 | False | 0 | 3.40 | 2.59 |
| 10 | 0 | complete | 263.270 | 263.180 | 26 | False | 0 | 2.59 | 3.51 |
| 11 | 0 | complete | 262.283 | 262.190 | 26 | False | 0 | 3.51 | 3.09 |
| 12 | 0 | complete | 261.980 | 261.890 | 26 | False | 0 | 3.09 | 3.17 |
| 13 | 0 | complete | 262.117 | 262.020 | 26 | False | 0 | 3.17 | 2.72 |
| 14 | 0 | complete | 264.431 | 264.340 | 26 | False | 0 | 2.72 | 2.99 |
| 15 | 0 | complete | 263.713 | 263.620 | 26 | False | 0 | 2.99 | 2.63 |
| 16 | 0 | complete | 262.943 | 262.850 | 26 | False | 0 | 2.63 | 2.93 |
| 17 | 0 | complete | 263.369 | 263.280 | 26 | False | 0 | 2.93 | 2.78 |
| 18 | 0 | complete | 263.254 | 263.160 | 26 | False | 0 | 2.78 | 2.93 |
| 19 | 0 | complete | 270.878 | 270.780 | 26 | False | 0 | 2.93 | 2.80 |

