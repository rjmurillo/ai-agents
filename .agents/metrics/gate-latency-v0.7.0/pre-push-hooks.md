# Gate latency: pre-push (hooks)

- Commit: `610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af`
- Captured at: `2026-09-16T07:02:28.831005+00:00`
- Repetitions: 2
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class hooks --repetitions 2 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/ai-agents-goal-spec-ch26ls 610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af refs/heads/claude/ai-agents-goal-spec-ch26ls 659097d6d66c5e66aab76f9f2258bf2e333ee7b8 --json .agents/metrics/gate-latency-v0.7.0/pre-push-hooks.json --markdown .agents/metrics/gate-latency-v0.7.0/pre-push-hooks.md --allow-dirty
```

## Change class

- `hooks`: `build/scripts/generate_hooks.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=2 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

| scope | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|
| __hook__ | 2 | 123.922 | 121.789 | 121.789 |
| additions-advisory | 2 | 0.510 | 0.430 | 0.430 |
| bot-cascade-advisory | 2 | 0.730 | 0.660 | 0.660 |
| branch-context-policy | 2 | 0.390 | 0.360 | 0.360 |
| branch-scope | 2 | 0.350 | 0.290 | 0.290 |
| count-ratchets | 2 | 22.720 | 22.450 | 22.450 |
| dash-prohibition | 2 | 0.720 | 0.660 | 0.660 |
| group (4) | 2 | 1.490 | 1.340 | 1.340 |
| group (5) | 2 | 37.410 | 36.390 | 36.390 |
| group (7) | 2 | 130.020 | 127.260 | 127.260 |
| hook-anchoring-e2e | 2 | 0.530 | 0.500 | 0.500 |
| infrastructure-advisory | 2 | 0.280 | 0.240 | 0.240 |
| mutation-safety | 2 | 0.090 | 0.090 | 0.090 |
| path-normalization | 2 | 3.770 | 3.610 | 3.610 |
| placeholder-identity | 2 | 0.310 | 0.290 | 0.290 |
| planning-artifacts | 2 | 0.190 | 0.180 | 0.180 |
| pre-pr-validation | 2 | 92.200 | 90.280 | 90.280 |
| push-ref-policy | 2 | 0.960 | 0.830 | 0.830 |
| push-ref-staleness | 2 | 1.200 | 0.910 | 0.910 |
| python-lint-advisory | 2 | 0.120 | 0.080 | 0.080 |
| python-tests | 2 | 15.750 | 14.920 | 14.920 |
| python-type-check | 2 | 0.450 | 0.410 | 0.410 |
| python-unreachable-statements | 2 | 9.290 | 8.360 | 8.360 |
| repair-packed-refs | 2 | 0.080 | 0.080 | 0.080 |
| repo-health | 2 | 0.080 | 0.080 | 0.080 |
| review-axis-drift | 2 | 0.260 | 0.190 | 0.190 |
| security-scan | 2 | 6.270 | 6.210 | 6.210 |
| security-suppression-policy | 2 | 0.220 | 0.220 | 0.220 |
| worktree-gc-report | 2 | 1.040 | 0.990 | 0.990 |
| zero-collection-tests | 2 | 18.640 | 18.530 | 18.530 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 121.789 | 121.720 | 29 | False | 0 |
| 1 | 0 | 123.922 | 123.860 | 29 | False | 0 |

