# Gate latency: pre-push (python)

- Commit: `0e98cb2d125635c1a7f71c7a89f70df0293a94ff`
- Captured at: `2026-10-23T07:54:15.633495+00:00`
- Repetitions: 20
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 4.41, 5.06, 4.54 (1/5/15 min); 0.09 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class python --repetitions 20 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/perf/6734-measure-scratch 0e98cb2d125635c1a7f71c7a89f70df0293a94ff refs/heads/perf/6734-measure-scratch 7d4ef439fae19671cbc3733ddca2312f0b4d61c9 --json ../perf-6734-out/pre-push-python.json --markdown ../perf-6734-out/pre-push-python.md
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
| __hook__ | hook wall clock | 20 | 263.270 | 265.607 | 261.552 | 266.175 |
| additions-advisory | job | 20 | 0.250 | 0.270 | 0.220 | 0.280 |
| bot-cascade-advisory | job | 20 | 0.710 | 0.900 | 0.630 | 0.960 |
| branch-config-prune-report | job | 20 | 0.230 | 0.240 | 0.200 | 0.240 |
| branch-context-policy | job | 20 | 0.240 | 0.270 | 0.220 | 0.270 |
| count-ratchets | job | 20 | 40.240 | 41.180 | 40.030 | 41.240 |
| dash-prohibition | job | 20 | 0.690 | 0.840 | 0.630 | 1.140 |
| group (4) | group total (sum) | 20 | 1.180 | 1.410 | 1.140 | 1.540 |
| group (5) | group total (sum) | 20 | 61.880 | 62.900 | 61.330 | 63.520 |
| group (7) | group total (sum) | 20 | 312.060 | 320.400 | 308.510 | 351.490 |
| mutation-safety | job | 20 | 0.090 | 0.090 | 0.090 | 0.090 |
| path-normalization | job | 20 | 3.300 | 3.350 | 3.280 | 3.350 |
| placeholder-identity | job | 20 | 0.300 | 0.310 | 0.300 | 0.320 |
| planning-artifacts | job | 20 | 0.090 | 0.110 | 0.070 | 0.110 |
| pre-pr-validation | job | 20 | 220.300 | 222.900 | 219.060 | 223.030 |
| push-ref-policy | job | 20 | 0.650 | 0.880 | 0.600 | 1.010 |
| push-ref-staleness | job | 20 | 0.410 | 0.540 | 0.370 | 0.940 |
| python-lint-advisory | job | 20 | 0.160 | 0.200 | 0.120 | 0.200 |
| python-tests | job | 20 | 53.120 | 60.530 | 51.230 | 93.270 |
| python-type-check | job | 20 | 0.260 | 0.270 | 0.220 | 0.270 |
| python-unreachable-statements | job | 20 | 16.900 | 17.390 | 16.710 | 17.810 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| review-axis-drift | job | 20 | 0.130 | 0.150 | 0.110 | 0.150 |
| security-scan | job | 20 | 0.540 | 0.550 | 0.540 | 0.550 |
| security-suppression-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.240 |
| worktree-gc-report | job | 20 | 0.630 | 0.680 | 0.570 | 0.770 |
| zero-collection-tests | job | 20 | 36.080 | 36.770 | 35.970 | 37.130 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 262.050 | 261.960 | 27 | False | 0 | 2.83 | 3.08 |
| 1 | 0 | complete | 261.552 | 261.460 | 27 | False | 0 | 3.08 | 3.81 |
| 2 | 0 | complete | 261.811 | 261.720 | 27 | False | 0 | 3.81 | 3.82 |
| 3 | 0 | complete | 265.342 | 265.250 | 27 | False | 0 | 3.82 | 6.35 |
| 4 | 0 | complete | 264.230 | 264.140 | 27 | False | 0 | 6.35 | 5.27 |
| 5 | 0 | complete | 262.612 | 262.520 | 27 | False | 0 | 5.27 | 4.33 |
| 6 | 0 | complete | 262.286 | 262.190 | 27 | False | 0 | 4.33 | 3.44 |
| 7 | 0 | complete | 263.559 | 263.460 | 27 | False | 0 | 3.44 | 2.82 |
| 8 | 0 | complete | 265.398 | 265.300 | 27 | False | 0 | 2.82 | 2.69 |
| 9 | 0 | complete | 266.175 | 266.080 | 27 | False | 0 | 2.69 | 2.82 |
| 10 | 0 | complete | 265.607 | 265.510 | 27 | False | 0 | 2.82 | 3.60 |
| 11 | 0 | complete | 262.998 | 262.900 | 27 | False | 0 | 3.60 | 2.56 |
| 12 | 0 | complete | 263.614 | 263.520 | 27 | False | 0 | 2.56 | 3.42 |
| 13 | 0 | complete | 263.270 | 263.180 | 27 | False | 0 | 3.42 | 3.38 |
| 14 | 0 | complete | 262.421 | 262.330 | 27 | False | 0 | 3.38 | 2.71 |
| 15 | 0 | complete | 262.450 | 262.360 | 27 | False | 0 | 2.71 | 2.80 |
| 16 | 0 | complete | 261.887 | 261.790 | 27 | False | 0 | 2.80 | 3.05 |
| 17 | 0 | complete | 263.499 | 263.400 | 27 | False | 0 | 3.05 | 3.77 |
| 18 | 0 | complete | 264.153 | 264.060 | 27 | False | 0 | 3.77 | 3.52 |
| 19 | 0 | complete | 265.520 | 265.430 | 27 | False | 0 | 3.52 | 4.53 |

