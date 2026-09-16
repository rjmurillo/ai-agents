# Gate latency: pre-push (python)

- Commit: `610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af`
- Captured at: `2026-09-16T07:06:38.705083+00:00`
- Repetitions: 2
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class python --repetitions 2 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/ai-agents-goal-spec-ch26ls 610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af refs/heads/claude/ai-agents-goal-spec-ch26ls 659097d6d66c5e66aab76f9f2258bf2e333ee7b8 --json .agents/metrics/gate-latency-v0.7.0/pre-push-python.json --markdown .agents/metrics/gate-latency-v0.7.0/pre-push-python.md --allow-dirty
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=2 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

| scope | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|
| __hook__ | 2 | 125.831 | 123.623 | 123.623 |
| additions-advisory | 2 | 0.480 | 0.440 | 0.440 |
| bot-cascade-advisory | 2 | 0.820 | 0.650 | 0.650 |
| branch-context-policy | 2 | 0.340 | 0.320 | 0.320 |
| branch-scope | 2 | 0.300 | 0.290 | 0.290 |
| count-ratchets | 2 | 23.820 | 23.070 | 23.070 |
| dash-prohibition | 2 | 0.670 | 0.660 | 0.660 |
| group (4) | 2 | 1.520 | 1.270 | 1.270 |
| group (5) | 2 | 39.590 | 37.140 | 37.140 |
| group (7) | 2 | 130.290 | 129.220 | 129.220 |
| infrastructure-advisory | 2 | 0.260 | 0.200 | 0.200 |
| mutation-safety | 2 | 0.100 | 0.100 | 0.100 |
| path-normalization | 2 | 3.600 | 3.520 | 3.520 |
| placeholder-identity | 2 | 0.300 | 0.290 | 0.290 |
| planning-artifacts | 2 | 0.180 | 0.140 | 0.140 |
| pre-pr-validation | 2 | 92.880 | 92.050 | 92.050 |
| push-ref-policy | 2 | 0.990 | 0.770 | 0.770 |
| push-ref-staleness | 2 | 0.990 | 0.680 | 0.680 |
| python-lint-advisory | 2 | 0.100 | 0.050 | 0.050 |
| python-tests | 2 | 15.570 | 15.300 | 15.300 |
| python-type-check | 2 | 0.400 | 0.350 | 0.350 |
| python-unreachable-statements | 2 | 10.580 | 8.750 | 8.750 |
| repair-packed-refs | 2 | 0.080 | 0.080 | 0.080 |
| repo-health | 2 | 0.080 | 0.080 | 0.080 |
| review-axis-drift | 2 | 0.270 | 0.230 | 0.230 |
| security-scan | 2 | 6.290 | 6.220 | 6.220 |
| security-suppression-policy | 2 | 0.220 | 0.210 | 0.210 |
| worktree-gc-report | 2 | 1.110 | 1.090 | 1.090 |
| zero-collection-tests | 2 | 18.880 | 18.870 | 18.870 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 125.831 | 125.770 | 28 | False | 0 |
| 1 | 0 | 123.623 | 123.560 | 28 | False | 0 |

