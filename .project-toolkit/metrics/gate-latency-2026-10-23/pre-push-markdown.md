# Gate latency: pre-push (markdown)

- Commit: `0e98cb2d125635c1a7f71c7a89f70df0293a94ff`
- Captured at: `2026-10-23T06:26:23.240890+00:00`
- Repetitions: 20
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 2.83, 4.27, 5.64 (1/5/15 min); 0.06 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class markdown --repetitions 20 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/perf/6734-measure-scratch 0e98cb2d125635c1a7f71c7a89f70df0293a94ff refs/heads/perf/6734-measure-scratch 7d4ef439fae19671cbc3733ddca2312f0b4d61c9 --json ../perf-6734-out/pre-push-markdown.json --markdown ../perf-6734-out/pre-push-markdown.md
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
| __hook__ | hook wall clock | 20 | 263.207 | 280.195 | 261.625 | 388.541 |
| additions-advisory | job | 20 | 0.240 | 0.250 | 0.220 | 0.250 |
| bot-cascade-advisory | job | 20 | 0.680 | 0.780 | 0.590 | 0.780 |
| branch-config-prune-report | job | 20 | 0.220 | 0.230 | 0.200 | 0.240 |
| branch-context-policy | job | 20 | 0.250 | 0.270 | 0.230 | 0.270 |
| count-ratchets | job | 20 | 40.430 | 41.310 | 40.080 | 41.830 |
| dash-prohibition | job | 20 | 0.690 | 0.770 | 0.640 | 0.960 |
| group (4) | group total (sum) | 20 | 1.170 | 1.370 | 1.130 | 2.250 |
| group (5) | group total (sum) | 20 | 61.980 | 63.390 | 61.370 | 63.490 |
| group (7) | group total (sum) | 20 | 312.310 | 357.160 | 309.750 | 546.990 |
| mutation-safety | job | 20 | 0.090 | 0.090 | 0.090 | 0.090 |
| path-normalization | job | 20 | 3.300 | 3.370 | 3.250 | 3.420 |
| placeholder-identity | job | 20 | 0.300 | 0.310 | 0.300 | 0.310 |
| planning-artifacts | job | 20 | 0.090 | 0.110 | 0.070 | 0.110 |
| pre-pr-validation | job | 20 | 220.390 | 235.830 | 218.620 | 345.120 |
| push-ref-policy | job | 20 | 0.630 | 0.840 | 0.600 | 1.710 |
| push-ref-staleness | job | 20 | 0.400 | 0.450 | 0.350 | 0.470 |
| python-tests | job | 20 | 54.160 | 89.790 | 51.970 | 163.420 |
| python-unreachable-statements | job | 20 | 17.040 | 17.380 | 16.840 | 17.720 |
| repair-packed-refs | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| review-axis-drift | job | 20 | 0.130 | 0.150 | 0.120 | 0.150 |
| security-scan | job | 20 | 0.550 | 0.560 | 0.540 | 0.560 |
| security-suppression-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| worktree-gc-report | job | 20 | 0.610 | 0.770 | 0.560 | 1.280 |
| zero-collection-tests | job | 20 | 36.270 | 36.940 | 36.000 | 37.060 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 264.133 | 264.040 | 25 | False | 0 | 4.31 | 2.71 |
| 1 | 0 | complete | 261.625 | 261.530 | 25 | False | 0 | 2.71 | 3.14 |
| 2 | 0 | complete | 265.045 | 264.950 | 25 | False | 0 | 3.14 | 5.76 |
| 3 | 0 | complete | 261.730 | 261.640 | 25 | False | 0 | 5.76 | 3.04 |
| 4 | 0 | complete | 262.508 | 262.410 | 25 | False | 0 | 3.04 | 3.66 |
| 5 | 0 | complete | 263.015 | 262.920 | 25 | False | 0 | 3.66 | 3.52 |
| 6 | 0 | complete | 262.385 | 262.290 | 25 | False | 0 | 3.52 | 4.50 |
| 7 | 0 | complete | 262.432 | 262.340 | 25 | False | 0 | 4.50 | 4.51 |
| 8 | 0 | complete | 266.978 | 266.880 | 25 | False | 0 | 4.51 | 6.17 |
| 9 | 0 | complete | 264.385 | 264.290 | 25 | False | 0 | 6.17 | 4.21 |
| 10 | 0 | complete | 267.310 | 267.220 | 25 | False | 0 | 4.21 | 6.90 |
| 11 | 0 | complete | 263.374 | 263.280 | 25 | False | 0 | 6.90 | 5.84 |
| 12 | 0 | complete | 266.442 | 266.350 | 25 | False | 0 | 5.84 | 12.81 |
| 13 | 0 | complete | 388.541 | 388.440 | 25 | False | 0 | 12.81 | 4.54 |
| 14 | 0 | complete | 280.195 | 280.100 | 25 | False | 0 | 4.54 | 6.35 |
| 15 | 0 | complete | 263.770 | 263.670 | 25 | False | 0 | 6.35 | 4.61 |
| 16 | 0 | complete | 262.854 | 262.760 | 25 | False | 0 | 4.61 | 4.89 |
| 17 | 0 | complete | 263.133 | 263.040 | 25 | False | 0 | 4.89 | 6.26 |
| 18 | 0 | complete | 263.207 | 263.110 | 25 | False | 0 | 6.26 | 3.57 |
| 19 | 0 | complete | 262.489 | 262.390 | 25 | False | 0 | 3.57 | 2.83 |

