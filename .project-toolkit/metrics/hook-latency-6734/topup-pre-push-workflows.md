# Gate latency: pre-push (workflows)

- Commit: `d44913c9aa60a9de7f2346e0db953e2c1674aec6`
- Captured at: `2026-10-20T21:18:31.993422+00:00`
- Repetitions: 7
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v139-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7
- Load average: 0.94, 1.99, 2.40 (1/5/15 min); 0.24 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --repo <repo> --hook pre-push --change-class workflows --repetitions 7 --json <scratch>/topup-pre-push-workflows.json --markdown <scratch>/topup-pre-push-workflows.md --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/measure-6734-workflows d44913c9aa60a9de7f2346e0db953e2c1674aec6 refs/heads/claude/measure-6734-workflows 0000000000000000000000000000000000000000
```

## Change class

- `workflows`: `.github/workflows/pytest.yml`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=7 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 7 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 7 | 361.019 | 337.713 | 309.612 |
| additions-advisory | job | 7 | 0.790 | 0.560 | 0.460 |
| bot-cascade-advisory | job | 7 | 1.070 | 0.930 | 0.820 |
| branch-config-prune-report | job | 7 | 0.780 | 0.640 | 0.490 |
| branch-context-policy | job | 7 | 0.470 | 0.440 | 0.350 |
| count-ratchets | job | 7 | 77.480 | 72.230 | 65.880 |
| dash-prohibition | job | 7 | 0.910 | 0.800 | 0.720 |
| group (4) | group total (sum) | 7 | 1.900 | 1.770 | 1.520 |
| group (5) | group total (sum) | 7 | 146.340 | 137.450 | 120.030 |
| group (7) | group total (sum) | 7 | 324.790 | 291.870 | 274.020 |
| mutation-safety | job | 7 | 0.150 | 0.130 | 0.110 |
| path-normalization | job | 7 | 19.800 | 14.430 | 13.720 |
| placeholder-identity | job | 7 | 0.430 | 0.400 | 0.330 |
| planning-artifacts | job | 7 | 0.330 | 0.260 | 0.190 |
| pre-pr-validation | job | 7 | 255.060 | 229.540 | 216.950 |
| push-ref-policy | job | 7 | 1.140 | 1.060 | 0.950 |
| push-ref-staleness | job | 7 | 0.700 | 0.600 | 0.520 |
| python-tests | job | 7 | 17.000 | 14.770 | 12.850 |
| python-unreachable-statements | job | 7 | 52.780 | 45.620 | 37.990 |
| repair-packed-refs | job | 7 | 0.110 | 0.100 | 0.090 |
| repo-health | job | 7 | 0.130 | 0.100 | 0.090 |
| review-axis-drift | job | 7 | 0.400 | 0.330 | 0.220 |
| security-scan | job | 7 | 46.180 | 26.110 | 20.930 |
| security-suppression-policy | job | 7 | 0.340 | 0.300 | 0.240 |
| workflow-local-run | job | 7 | 0.860 | 0.730 | 0.580 |
| worktree-gc-report | job | 7 | 1.350 | 1.280 | 1.080 |
| zero-collection-tests | job | 7 | 48.010 | 42.930 | 40.170 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 352.627 | 352.460 | 26 | False | 0 | 0.06 | 0.95 |
| 1 | 0 | complete | 361.019 | 360.880 | 26 | False | 0 | 0.95 | 0.97 |
| 2 | 0 | complete | 355.103 | 354.970 | 26 | False | 0 | 0.97 | 0.94 |
| 3 | 0 | complete | 333.013 | 332.890 | 26 | False | 0 | 0.94 | 0.98 |
| 4 | 0 | complete | 337.713 | 337.590 | 26 | False | 0 | 0.98 | 0.98 |
| 5 | 0 | complete | 312.226 | 312.100 | 26 | False | 0 | 0.98 | 1.04 |
| 6 | 0 | complete | 309.612 | 309.500 | 26 | False | 0 | 1.04 | 0.94 |

