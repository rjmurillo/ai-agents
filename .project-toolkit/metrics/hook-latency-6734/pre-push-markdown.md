# Gate latency: pre-push (markdown)

- Commit: `05966ee5573c5a8c6a1cf974e3212454649de8d7`
- Captured at: `2026-10-20T18:18:50.811850+00:00`
- Repetitions: 21
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v139-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7
- Load average: 0.98, 2.09, 2.49 (1/5/15 min); 0.25 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --repo <repo> --hook pre-push --change-class markdown --repetitions 21 --json <scratch>/full-pre-push-markdown.json --markdown <scratch>/full-pre-push-markdown.md --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/measure-6734-markdown 05966ee5573c5a8c6a1cf974e3212454649de8d7 refs/heads/claude/measure-6734-markdown 0000000000000000000000000000000000000000
```

## Change class

- `markdown`: `README.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 21 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 21 | 328.642 | 350.336 | 307.614 | 354.485 |
| additions-advisory | job | 21 | 0.480 | 0.560 | 0.330 | 0.570 |
| bot-cascade-advisory | job | 21 | 0.820 | 0.870 | 0.740 | 0.960 |
| branch-config-prune-report | job | 21 | 0.480 | 0.540 | 0.310 | 0.540 |
| branch-context-policy | job | 21 | 0.430 | 0.550 | 0.330 | 0.630 |
| count-ratchets | job | 21 | 72.840 | 79.750 | 67.670 | 80.240 |
| dash-prohibition | job | 21 | 0.800 | 0.910 | 0.680 | 0.970 |
| group (4) | group total (sum) | 21 | 1.600 | 1.780 | 1.440 | 1.890 |
| group (5) | group total (sum) | 21 | 131.580 | 141.980 | 116.060 | 143.640 |
| group (7) | group total (sum) | 21 | 331.050 | 359.630 | 300.330 | 361.980 |
| mutation-safety | job | 21 | 0.110 | 0.140 | 0.100 | 0.150 |
| path-normalization | job | 21 | 15.040 | 16.710 | 7.480 | 17.170 |
| placeholder-identity | job | 21 | 0.380 | 0.420 | 0.340 | 0.440 |
| planning-artifacts | job | 21 | 0.220 | 0.270 | 0.100 | 0.280 |
| pre-pr-validation | job | 21 | 254.390 | 270.100 | 235.060 | 273.500 |
| push-ref-policy | job | 21 | 0.940 | 1.120 | 0.850 | 1.190 |
| push-ref-staleness | job | 21 | 0.550 | 1.570 | 0.490 | 1.580 |
| python-tests | job | 21 | 34.500 | 49.230 | 14.270 | 49.390 |
| python-unreachable-statements | job | 21 | 42.150 | 47.330 | 33.710 | 50.690 |
| repair-packed-refs | job | 21 | 0.100 | 0.110 | 0.080 | 0.120 |
| repo-health | job | 21 | 0.090 | 0.110 | 0.080 | 0.110 |
| review-axis-drift | job | 21 | 0.280 | 0.380 | 0.170 | 0.390 |
| security-scan | job | 21 | 0.570 | 0.690 | 0.520 | 0.710 |
| security-suppression-policy | job | 21 | 0.270 | 0.330 | 0.240 | 0.350 |
| worktree-gc-report | job | 21 | 1.120 | 2.080 | 0.930 | 2.180 |
| zero-collection-tests | job | 21 | 42.460 | 43.730 | 39.250 | 45.070 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 334.949 | 334.820 | 25 | False | 0 | 0.85 | 0.81 |
| 1 | 0 | complete | 354.485 | 354.360 | 25 | False | 0 | 0.81 | 0.87 |
| 2 | 0 | complete | 350.336 | 350.220 | 25 | False | 0 | 0.87 | 0.86 |
| 3 | 0 | complete | 333.154 | 333.040 | 25 | False | 0 | 0.86 | 0.89 |
| 4 | 0 | complete | 327.763 | 327.630 | 25 | False | 0 | 0.89 | 0.88 |
| 5 | 0 | complete | 328.642 | 328.530 | 25 | False | 0 | 0.88 | 1.19 |
| 6 | 0 | complete | 323.886 | 323.760 | 25 | False | 0 | 1.19 | 0.90 |
| 7 | 0 | complete | 343.113 | 342.960 | 25 | False | 0 | 0.90 | 0.81 |
| 8 | 0 | complete | 339.642 | 339.520 | 25 | False | 0 | 0.81 | 0.94 |
| 9 | 0 | complete | 312.805 | 312.690 | 25 | False | 0 | 0.94 | 0.96 |
| 10 | 0 | complete | 324.884 | 324.740 | 25 | False | 0 | 0.96 | 1.01 |
| 11 | 0 | complete | 327.753 | 327.630 | 25 | False | 0 | 1.01 | 1.12 |
| 12 | 0 | complete | 311.306 | 311.190 | 25 | False | 0 | 1.12 | 1.00 |
| 13 | 0 | complete | 333.245 | 333.140 | 25 | False | 0 | 1.00 | 0.82 |
| 14 | 0 | complete | 342.842 | 342.710 | 25 | False | 0 | 0.82 | 0.87 |
| 15 | 0 | complete | 313.169 | 313.060 | 25 | False | 0 | 0.87 | 1.10 |
| 16 | 0 | complete | 330.855 | 330.730 | 25 | False | 0 | 1.10 | 0.97 |
| 17 | 0 | complete | 309.934 | 309.780 | 25 | False | 0 | 0.97 | 0.96 |
| 18 | 0 | complete | 317.183 | 317.070 | 25 | False | 0 | 0.96 | 0.92 |
| 19 | 0 | complete | 307.614 | 307.480 | 25 | False | 0 | 0.92 | 0.89 |
| 20 | 0 | complete | 348.994 | 348.870 | 25 | False | 0 | 0.89 | 0.98 |

