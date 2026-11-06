# Gate latency: pre-commit (markdown)

- Commit: `05966ee5573c5a8c6a1cf974e3212454649de8d7`
- Captured at: `2026-10-20T14:13:35.464641+00:00`
- Repetitions: 21
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v139-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7
- Load average: 1.22, 1.25, 1.28 (1/5/15 min); 0.30 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --repo <repo> --hook pre-commit --change-class markdown --repetitions 21 --json <scratch>/full-pre-commit-markdown.json --markdown <scratch>/full-pre-commit-markdown.md
```

## Change class

- `markdown`: `README.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 5815.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 21 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 21 | 34.199 | 35.543 | 31.641 | 35.659 |
| agents-write-targets | job | 21 | 27.760 | 29.200 | 25.360 | 29.560 |
| branch-context-policy | job | 21 | 0.300 | 0.370 | 0.250 | 0.390 |
| branch-policy | job | 21 | 0.300 | 0.360 | 0.250 | 0.380 |
| conflict-marker-policy | job | 21 | 0.540 | 0.650 | 0.360 | 0.740 |
| context-output-check | job | 21 | 1.310 | 1.410 | 1.190 | 1.490 |
| group (14) | group total (sum) | 21 | 1.310 | 1.410 | 1.190 | 1.490 |
| group (5) | group total (sum) | 21 | 3.760 | 4.220 | 3.230 | 4.380 |
| group (6) | group total (sum) | 21 | 31.000 | 32.380 | 27.890 | 32.530 |
| infrastructure-advisory | job | 21 | 0.240 | 0.370 | 0.130 | 0.410 |
| markdown-autofix | job | 21 | 1.910 | 2.130 | 1.580 | 2.280 |
| markdown-check | job | 21 | 1.880 | 2.150 | 1.650 | 2.190 |
| push-lock-commit-guard | job | 21 | 0.110 | 0.130 | 0.090 | 0.130 |
| python-format | job | 21 | 0.110 | 0.190 | 0.040 | 0.210 |
| repair-packed-refs | job | 21 | 0.110 | 0.140 | 0.090 | 0.140 |
| repo-health | job | 21 | 0.100 | 0.130 | 0.090 | 0.150 |
| root-hygiene-policy | job | 21 | 0.490 | 0.620 | 0.370 | 0.620 |
| root-scratch-policy | job | 21 | 0.510 | 0.660 | 0.370 | 0.680 |
| staged-dash-policy | job | 21 | 0.510 | 0.640 | 0.300 | 0.710 |
| taste-advisory | job | 21 | 0.650 | 0.750 | 0.400 | 0.770 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 33.199 | 33.060 | 19 | False | 0 | 0.69 | 0.96 |
| 1 | 0 | complete | 33.855 | 33.740 | 19 | False | 0 | 0.96 | 0.98 |
| 2 | 0 | complete | 34.299 | 34.160 | 19 | False | 0 | 0.98 | 0.99 |
| 3 | 0 | complete | 33.767 | 33.630 | 19 | False | 0 | 0.99 | 0.99 |
| 4 | 0 | complete | 34.288 | 34.140 | 19 | False | 0 | 0.99 | 1.00 |
| 5 | 0 | complete | 33.925 | 33.730 | 19 | False | 0 | 1.00 | 1.06 |
| 6 | 0 | complete | 34.428 | 34.280 | 19 | False | 0 | 1.06 | 1.03 |
| 7 | 0 | complete | 33.841 | 33.700 | 19 | False | 0 | 1.03 | 1.02 |
| 8 | 0 | complete | 31.984 | 31.830 | 19 | False | 0 | 1.02 | 1.06 |
| 9 | 0 | complete | 34.213 | 34.080 | 19 | False | 0 | 1.06 | 1.29 |
| 10 | 0 | complete | 31.641 | 31.490 | 19 | False | 0 | 1.29 | 1.17 |
| 11 | 0 | complete | 32.190 | 32.050 | 19 | False | 0 | 1.17 | 1.09 |
| 12 | 0 | complete | 34.199 | 34.070 | 19 | False | 0 | 1.09 | 1.05 |
| 13 | 0 | complete | 35.189 | 35.050 | 19 | False | 0 | 1.05 | 1.04 |
| 14 | 0 | complete | 34.931 | 34.790 | 19 | False | 0 | 1.04 | 0.98 |
| 15 | 0 | complete | 35.543 | 35.400 | 19 | False | 0 | 0.98 | 0.99 |
| 16 | 0 | complete | 32.975 | 32.830 | 19 | False | 0 | 0.99 | 0.99 |
| 17 | 0 | complete | 35.659 | 35.500 | 19 | False | 0 | 0.99 | 1.34 |
| 18 | 0 | complete | 35.059 | 34.930 | 19 | False | 0 | 1.34 | 1.30 |
| 19 | 0 | complete | 35.444 | 35.280 | 19 | False | 0 | 1.30 | 1.36 |
| 20 | 0 | complete | 31.972 | 31.840 | 19 | False | 0 | 1.36 | 1.22 |

