# Gate latency: pre-push (python)

- Commit: `5fbdfd238bd4eb64b6adfa3791b2fff3554db060`
- Captured at: `2026-11-10T02:22:13.473281+00:00`
- Repetitions: 20
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-43-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 9.96, 10.89, 15.77 (1/5/15 min); 0.21 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class python --repetitions 20 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/chore/5456-v0.7.0-close 5fbdfd238bd4eb64b6adfa3791b2fff3554db060 refs/heads/chore/5456-v0.7.0-close d6c1419104c5f96bbfd9c7ba6d77e89694ed0d53 --json .project-toolkit/metrics/gate-latency-2026-11-10/pre-push-python.json --markdown .project-toolkit/metrics/gate-latency-2026-11-10/pre-push-python.md
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
| __hook__ | hook wall clock | 20 | 106.151 | 201.730 | 100.932 | 245.580 |
| additions-advisory | job | 20 | 0.230 | 0.300 | 0.180 | 0.310 |
| bot-cascade-advisory | job | 20 | 0.640 | 0.760 | 0.570 | 0.780 |
| branch-config-prune-report | job | 20 | 0.250 | 0.300 | 0.210 | 0.300 |
| branch-context-policy | job | 20 | 0.200 | 0.310 | 0.180 | 0.350 |
| count-ratchets | job | 20 | 27.240 | 28.300 | 26.570 | 29.330 |
| dash-prohibition | job | 20 | 1.220 | 1.790 | 1.020 | 2.130 |
| group (4) | group total (sum) | 20 | 1.040 | 1.300 | 0.980 | 1.320 |
| group (5) | group total (sum) | 20 | 18.780 | 22.860 | 18.310 | 26.800 |
| group (7) | group total (sum) | 20 | 255.640 | 381.700 | 246.120 | 448.520 |
| import-boundaries | job | 20 | 0.400 | 0.600 | 0.320 | 0.610 |
| mutation-safety | job | 20 | 0.080 | 0.100 | 0.070 | 0.110 |
| path-normalization | job | 20 | 3.480 | 4.430 | 3.360 | 5.510 |
| placeholder-identity | job | 20 | 0.240 | 0.310 | 0.230 | 0.370 |
| planning-artifacts | job | 20 | 0.100 | 0.130 | 0.060 | 0.180 |
| plugin-scanner | job | 20 | 48.180 | 51.460 | 47.170 | 53.540 |
| pre-pr-validation | job | 20 | 91.660 | 186.130 | 86.420 | 228.310 |
| push-ref-policy | job | 20 | 0.610 | 0.830 | 0.570 | 0.870 |
| push-ref-staleness | job | 20 | 0.400 | 0.650 | 0.360 | 0.950 |
| python-lint-advisory | job | 20 | 0.200 | 0.230 | 0.160 | 0.230 |
| python-tests | job | 20 | 55.820 | 99.940 | 54.620 | 110.510 |
| python-type-check | job | 20 | 0.210 | 0.280 | 0.170 | 0.290 |
| python-unreachable-statements | job | 20 | 12.490 | 15.040 | 12.220 | 17.280 |
| python-unused-arguments | job | 20 | 0.720 | 1.200 | 0.650 | 1.310 |
| repair-packed-refs | job | 20 | 0.070 | 0.080 | 0.060 | 0.100 |
| repo-health | job | 20 | 0.060 | 0.080 | 0.060 | 0.090 |
| review-axis-drift | job | 20 | 0.120 | 0.240 | 0.100 | 0.260 |
| security-scan | job | 20 | 0.420 | 0.480 | 0.410 | 0.610 |
| security-suppression-policy | job | 20 | 0.180 | 0.230 | 0.170 | 0.240 |
| worktree-gc-report | job | 20 | 0.830 | 1.070 | 0.760 | 4.200 |
| zero-collection-tests | job | 20 | 30.130 | 34.210 | 28.940 | 70.760 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 107.131 | 107.010 | 30 | False | 0 | 27.29 | 21.47 |
| 1 | 0 | complete | 201.730 | 201.600 | 30 | False | 0 | 21.67 | 32.49 |
| 2 | 0 | complete | 150.336 | 150.210 | 30 | False | 0 | 32.49 | 21.47 |
| 3 | 0 | complete | 161.342 | 161.210 | 30 | False | 0 | 21.47 | 22.75 |
| 4 | 0 | complete | 176.892 | 176.700 | 30 | False | 0 | 22.75 | 25.05 |
| 5 | 0 | complete | 104.436 | 104.310 | 30 | False | 0 | 25.05 | 21.20 |
| 6 | 0 | complete | 245.580 | 245.450 | 30 | False | 0 | 21.20 | 17.93 |
| 7 | 0 | complete | 143.538 | 143.410 | 30 | False | 0 | 17.93 | 13.70 |
| 8 | 0 | complete | 106.151 | 106.020 | 30 | False | 0 | 13.70 | 20.51 |
| 9 | 0 | complete | 103.846 | 103.720 | 30 | False | 0 | 20.51 | 14.06 |
| 10 | 0 | complete | 102.671 | 102.540 | 30 | False | 0 | 14.06 | 18.09 |
| 11 | 0 | complete | 190.039 | 189.910 | 30 | False | 0 | 18.09 | 17.61 |
| 12 | 0 | complete | 103.234 | 103.110 | 30 | False | 0 | 17.61 | 15.76 |
| 13 | 0 | complete | 102.544 | 102.420 | 30 | False | 0 | 15.76 | 14.72 |
| 14 | 0 | complete | 106.841 | 106.710 | 30 | False | 0 | 14.72 | 17.18 |
| 15 | 0 | complete | 146.534 | 146.400 | 30 | False | 0 | 17.18 | 15.44 |
| 16 | 0 | complete | 102.927 | 102.800 | 30 | False | 0 | 15.44 | 8.88 |
| 17 | 0 | complete | 100.932 | 100.800 | 30 | False | 0 | 8.88 | 4.98 |
| 18 | 0 | complete | 101.030 | 100.900 | 30 | False | 0 | 4.98 | 4.17 |
| 19 | 0 | complete | 103.242 | 103.110 | 30 | False | 0 | 4.17 | 9.96 |

