# Gate latency: pre-push (markdown)

- Commit: `610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af`
- Captured at: `2026-09-16T06:54:17.385739+00:00`
- Repetitions: 2
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class markdown --repetitions 2 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/ai-agents-goal-spec-ch26ls 610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af refs/heads/claude/ai-agents-goal-spec-ch26ls 659097d6d66c5e66aab76f9f2258bf2e333ee7b8 --json .agents/metrics/gate-latency-v0.7.0/pre-push-markdown.json --markdown .agents/metrics/gate-latency-v0.7.0/pre-push-markdown.md --allow-dirty
```

## Change class

- `markdown`: `README.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=2 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

| scope | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|
| __hook__ | 2 | 122.834 | 121.881 | 121.881 |
| additions-advisory | 2 | 0.340 | 0.310 | 0.310 |
| bot-cascade-advisory | 2 | 0.640 | 0.610 | 0.610 |
| branch-context-policy | 2 | 0.400 | 0.310 | 0.310 |
| branch-scope | 2 | 0.330 | 0.280 | 0.280 |
| count-ratchets | 2 | 22.530 | 22.170 | 22.170 |
| dash-prohibition | 2 | 0.730 | 0.500 | 0.500 |
| group (4) | 2 | 1.230 | 1.220 | 1.220 |
| group (5) | 2 | 36.390 | 35.690 | 35.690 |
| group (7) | 2 | 127.230 | 126.800 | 126.800 |
| infrastructure-advisory | 2 | 0.190 | 0.150 | 0.150 |
| mutation-safety | 2 | 0.090 | 0.090 | 0.090 |
| path-normalization | 2 | 3.580 | 3.000 | 3.000 |
| placeholder-identity | 2 | 0.310 | 0.280 | 0.280 |
| planning-artifacts | 2 | 0.180 | 0.170 | 0.170 |
| pre-pr-validation | 2 | 91.200 | 90.860 | 90.860 |
| push-ref-policy | 2 | 0.730 | 0.720 | 0.720 |
| push-ref-staleness | 2 | 0.800 | 0.680 | 0.680 |
| python-tests | 2 | 15.520 | 15.390 | 15.390 |
| python-unreachable-statements | 2 | 8.960 | 8.540 | 8.540 |
| repair-packed-refs | 2 | 0.080 | 0.080 | 0.080 |
| repo-health | 2 | 0.070 | 0.070 | 0.070 |
| review-axis-drift | 2 | 0.210 | 0.190 | 0.190 |
| security-scan | 2 | 7.120 | 6.310 | 6.310 |
| security-suppression-policy | 2 | 0.210 | 0.200 | 0.200 |
| worktree-gc-report | 2 | 1.010 | 0.870 | 0.870 |
| zero-collection-tests | 2 | 18.740 | 18.210 | 18.210 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 121.881 | 121.830 | 26 | False | 0 |
| 1 | 0 | 122.834 | 122.780 | 26 | False | 0 |

