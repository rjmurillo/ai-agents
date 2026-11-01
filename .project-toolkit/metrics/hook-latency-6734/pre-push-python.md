# Gate latency: pre-push (python)

- Commit: `90af99ede2f77057edaa885d0d64d19a62cda634`
- Captured at: `2026-10-20T20:15:50.386572+00:00`
- Repetitions: 21
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v139-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7
- Load average: 0.94, 1.95, 2.42 (1/5/15 min); 0.23 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --repo <repo> --hook pre-push --change-class python --repetitions 21 --json <scratch>/full-pre-push-python.json --markdown <scratch>/full-pre-push-python.md --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/measure-6734-python 90af99ede2f77057edaa885d0d64d19a62cda634 refs/heads/claude/measure-6734-python 0000000000000000000000000000000000000000
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 21 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 21 | 326.968 | 367.370 | 303.551 | 383.442 |
| additions-advisory | job | 21 | 0.580 | 0.700 | 0.450 | 0.700 |
| bot-cascade-advisory | job | 21 | 0.970 | 1.110 | 0.770 | 1.120 |
| branch-config-prune-report | job | 21 | 0.610 | 0.710 | 0.410 | 0.730 |
| branch-context-policy | job | 21 | 0.420 | 0.580 | 0.290 | 0.590 |
| count-ratchets | job | 21 | 71.080 | 80.280 | 63.720 | 82.810 |
| dash-prohibition | job | 21 | 0.780 | 0.900 | 0.570 | 0.910 |
| group (4) | group total (sum) | 21 | 1.640 | 2.200 | 1.470 | 3.060 |
| group (5) | group total (sum) | 21 | 128.430 | 150.080 | 118.220 | 156.600 |
| group (7) | group total (sum) | 21 | 294.460 | 316.530 | 273.270 | 321.390 |
| mutation-safety | job | 21 | 0.120 | 0.140 | 0.100 | 0.150 |
| path-normalization | job | 21 | 14.810 | 18.350 | 12.450 | 18.640 |
| placeholder-identity | job | 21 | 0.390 | 0.440 | 0.330 | 0.450 |
| planning-artifacts | job | 21 | 0.240 | 0.300 | 0.100 | 0.300 |
| pre-pr-validation | job | 21 | 231.500 | 249.650 | 215.340 | 250.400 |
| push-ref-policy | job | 21 | 0.960 | 1.520 | 0.850 | 2.320 |
| push-ref-staleness | job | 21 | 0.560 | 0.780 | 0.490 | 0.810 |
| python-lint-advisory | job | 21 | 0.380 | 0.520 | 0.280 | 0.560 |
| python-tests | job | 21 | 15.180 | 18.730 | 13.430 | 19.270 |
| python-type-check | job | 21 | 0.800 | 0.890 | 0.480 | 1.010 |
| python-unreachable-statements | job | 21 | 41.950 | 49.410 | 36.940 | 53.740 |
| repair-packed-refs | job | 21 | 0.100 | 0.120 | 0.090 | 0.130 |
| repo-health | job | 21 | 0.100 | 0.140 | 0.080 | 0.140 |
| review-axis-drift | job | 21 | 0.330 | 0.370 | 0.230 | 0.390 |
| security-scan | job | 21 | 21.210 | 52.380 | 13.090 | 59.840 |
| security-suppression-policy | job | 21 | 0.280 | 0.320 | 0.260 | 0.340 |
| worktree-gc-report | job | 21 | 1.240 | 1.820 | 1.040 | 2.580 |
| zero-collection-tests | job | 21 | 42.600 | 45.840 | 39.550 | 48.160 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 308.323 | 308.210 | 27 | False | 0 | 0.98 | 0.99 |
| 1 | 0 | complete | 360.958 | 360.840 | 27 | False | 0 | 0.99 | 1.04 |
| 2 | 0 | complete | 303.551 | 303.440 | 27 | False | 0 | 1.04 | 1.02 |
| 3 | 0 | complete | 317.077 | 316.970 | 27 | False | 0 | 1.02 | 1.17 |
| 4 | 0 | complete | 318.421 | 318.300 | 27 | False | 0 | 1.17 | 0.93 |
| 5 | 0 | complete | 308.959 | 308.830 | 27 | False | 0 | 0.93 | 0.98 |
| 6 | 0 | complete | 315.671 | 315.530 | 27 | False | 0 | 0.98 | 0.96 |
| 7 | 0 | complete | 351.144 | 351.020 | 27 | False | 0 | 0.96 | 1.19 |
| 8 | 0 | complete | 310.567 | 310.450 | 27 | False | 0 | 1.19 | 1.08 |
| 9 | 0 | complete | 330.152 | 330.020 | 27 | False | 0 | 1.08 | 1.03 |
| 10 | 0 | complete | 338.372 | 338.230 | 27 | False | 0 | 1.03 | 1.03 |
| 11 | 0 | complete | 367.370 | 367.250 | 27 | False | 0 | 1.03 | 0.99 |
| 12 | 0 | complete | 383.442 | 383.310 | 27 | False | 0 | 0.99 | 0.88 |
| 13 | 0 | complete | 326.968 | 326.850 | 27 | False | 0 | 0.88 | 0.92 |
| 14 | 0 | complete | 358.097 | 357.990 | 27 | False | 0 | 0.92 | 0.98 |
| 15 | 0 | complete | 323.896 | 323.780 | 27 | False | 0 | 0.98 | 0.80 |
| 16 | 0 | complete | 320.467 | 320.340 | 27 | False | 0 | 0.80 | 1.08 |
| 17 | 0 | complete | 357.738 | 357.610 | 27 | False | 0 | 1.08 | 0.95 |
| 18 | 0 | complete | 352.002 | 351.870 | 27 | False | 0 | 0.95 | 0.92 |
| 19 | 0 | complete | 324.269 | 324.130 | 27 | False | 0 | 0.92 | 0.94 |
| 20 | 0 | complete | 339.565 | 339.450 | 27 | False | 0 | 0.94 | 0.94 |

