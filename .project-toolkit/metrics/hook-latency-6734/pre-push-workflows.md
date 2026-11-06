# Gate latency: pre-push (workflows)

- Commit: `d44913c9aa60a9de7f2346e0db953e2c1674aec6`
- Captured at: `2026-10-20T16:23:31.798135+00:00`
- Repetitions: 21
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v139-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7
- Load average: 0.85, 1.95, 2.49 (1/5/15 min); 0.21 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --repo <repo> --hook pre-push --change-class workflows --repetitions 21 --json <scratch>/full-pre-push-workflows.json --markdown <scratch>/full-pre-push-workflows.md --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/measure-6734-workflows d44913c9aa60a9de7f2346e0db953e2c1674aec6 refs/heads/claude/measure-6734-workflows 0000000000000000000000000000000000000000
```

## Change class

- `workflows`: `.github/workflows/pytest.yml`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=16 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

5 of 21 repetitions were excluded from the summaries below because they did not measure the whole hook (5 truncated); see the per-repetition table for which repetition was which (REQ-027 D1).

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 16 | 396.564 | 362.679 | 324.162 |
| additions-advisory | job | 16 | 0.870 | 0.580 | 0.450 |
| bot-cascade-advisory | job | 16 | 2.100 | 0.920 | 0.810 |
| branch-config-prune-report | job | 16 | 0.780 | 0.560 | 0.340 |
| branch-context-policy | job | 16 | 0.550 | 0.450 | 0.360 |
| count-ratchets | job | 16 | 82.090 | 75.030 | 64.330 |
| dash-prohibition | job | 16 | 2.180 | 0.870 | 0.680 |
| group (4) | group total (sum) | 16 | 2.330 | 1.800 | 1.640 |
| group (5) | group total (sum) | 16 | 153.280 | 137.810 | 122.950 |
| group (7) | group total (sum) | 16 | 353.570 | 308.400 | 297.530 |
| mutation-safety | job | 16 | 0.160 | 0.120 | 0.100 |
| path-normalization | job | 16 | 19.900 | 15.590 | 10.910 |
| placeholder-identity | job | 16 | 0.570 | 0.400 | 0.370 |
| planning-artifacts | job | 16 | 0.300 | 0.170 | 0.120 |
| pre-pr-validation | job | 16 | 282.800 | 243.830 | 233.340 |
| push-ref-policy | job | 16 | 1.600 | 1.130 | 1.010 |
| push-ref-staleness | job | 16 | 0.670 | 0.580 | 0.500 |
| python-tests | job | 16 | 20.630 | 15.780 | 14.390 |
| python-unreachable-statements | job | 16 | 51.710 | 44.410 | 37.140 |
| repair-packed-refs | job | 16 | 0.140 | 0.100 | 0.080 |
| repo-health | job | 16 | 0.130 | 0.110 | 0.090 |
| review-axis-drift | job | 16 | 0.420 | 0.300 | 0.230 |
| security-scan | job | 16 | 42.100 | 27.110 | 12.090 |
| security-suppression-policy | job | 16 | 0.400 | 0.300 | 0.260 |
| workflow-local-run | job | 16 | 0.870 | 0.670 | 0.530 |
| worktree-gc-report | job | 16 | 4.080 | 1.310 | 1.030 |
| zero-collection-tests | job | 16 | 49.680 | 46.090 | 42.940 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 389.299 | 389.150 | 26 | False | 0 | 1.19 | 0.79 |
| 1 | 0 | complete | 373.280 | 373.150 | 26 | False | 0 | 0.81 | 1.02 |
| 2 | 1 | truncated | 89.007 | 88.880 | 16 | False | 0 | 1.02 | 7.16 |
| 3 | 1 | truncated | 388.198 | 388.080 | 26 | False | 0 | 7.16 | 0.86 |
| 4 | 0 | complete | 364.732 | 364.610 | 26 | False | 0 | 0.86 | 0.84 |
| 5 | 1 | truncated | 93.803 | 93.660 | 16 | False | 0 | 0.84 | 8.02 |
| 6 | 0 | complete | 396.564 | 396.400 | 26 | False | 0 | 8.02 | 1.11 |
| 7 | 0 | complete | 350.339 | 350.210 | 26 | False | 0 | 1.11 | 1.05 |
| 8 | 1 | truncated | 90.254 | 90.120 | 16 | False | 0 | 1.05 | 6.60 |
| 9 | 0 | complete | 369.529 | 369.400 | 26 | False | 0 | 6.60 | 0.94 |
| 10 | 0 | complete | 362.753 | 362.620 | 26 | False | 0 | 0.94 | 0.91 |
| 11 | 0 | complete | 365.005 | 364.880 | 26 | False | 0 | 0.91 | 1.04 |
| 12 | 0 | complete | 345.671 | 345.530 | 26 | False | 0 | 1.04 | 0.95 |
| 13 | 0 | complete | 368.975 | 368.850 | 26 | False | 0 | 0.95 | 0.97 |
| 14 | 0 | complete | 362.679 | 362.440 | 26 | False | 0 | 0.97 | 0.95 |
| 15 | 1 | truncated | 89.587 | 89.460 | 16 | False | 0 | 0.95 | 4.52 |
| 16 | 0 | complete | 341.434 | 341.320 | 26 | False | 0 | 4.52 | 0.97 |
| 17 | 0 | complete | 340.061 | 339.940 | 26 | False | 0 | 0.97 | 1.00 |
| 18 | 0 | complete | 336.598 | 336.490 | 26 | False | 0 | 1.00 | 0.99 |
| 19 | 0 | complete | 358.422 | 358.270 | 26 | False | 0 | 0.99 | 0.98 |
| 20 | 0 | complete | 324.162 | 324.040 | 26 | False | 0 | 0.98 | 0.85 |

