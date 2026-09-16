# Gate latency: pre-push (skills)

- Commit: `610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af`
- Captured at: `2026-09-16T06:58:22.755518+00:00`
- Repetitions: 2
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class skills --repetitions 2 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/ai-agents-goal-spec-ch26ls 610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af refs/heads/claude/ai-agents-goal-spec-ch26ls 659097d6d66c5e66aab76f9f2258bf2e333ee7b8 --json .agents/metrics/gate-latency-v0.7.0/pre-push-skills.json --markdown .agents/metrics/gate-latency-v0.7.0/pre-push-skills.md --allow-dirty
```

## Change class

- `skills`: `.claude/skills/spec/SKILL.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=2 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

| scope | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|
| __hook__ | 2 | 123.670 | 121.350 | 121.350 |
| additions-advisory | 2 | 0.390 | 0.290 | 0.290 |
| bot-cascade-advisory | 2 | 0.680 | 0.610 | 0.610 |
| branch-context-policy | 2 | 0.410 | 0.400 | 0.400 |
| branch-scope | 2 | 0.320 | 0.260 | 0.260 |
| count-ratchets | 2 | 23.520 | 22.610 | 22.610 |
| dash-prohibition | 2 | 0.710 | 0.680 | 0.680 |
| group (4) | 2 | 1.560 | 1.290 | 1.290 |
| group (5) | 2 | 38.820 | 36.980 | 36.980 |
| group (7) | 2 | 128.140 | 125.890 | 125.890 |
| infrastructure-advisory | 2 | 0.200 | 0.130 | 0.130 |
| mutation-safety | 2 | 0.090 | 0.090 | 0.090 |
| path-normalization | 2 | 3.810 | 3.650 | 3.650 |
| placeholder-identity | 2 | 0.310 | 0.280 | 0.280 |
| planning-artifacts | 2 | 0.180 | 0.140 | 0.140 |
| plugin-load-e2e | 2 | 0.410 | 0.380 | 0.380 |
| pre-pr-validation | 2 | 91.030 | 90.080 | 90.080 |
| push-ref-policy | 2 | 1.060 | 0.760 | 0.760 |
| push-ref-staleness | 2 | 0.980 | 0.940 | 0.940 |
| python-tests | 2 | 15.510 | 15.140 | 15.140 |
| python-unreachable-statements | 2 | 9.840 | 8.760 | 8.760 |
| repair-packed-refs | 2 | 0.090 | 0.070 | 0.070 |
| repo-health | 2 | 0.080 | 0.080 | 0.080 |
| review-axis-drift | 2 | 0.260 | 0.260 | 0.260 |
| security-scan | 2 | 6.310 | 6.090 | 6.090 |
| security-suppression-policy | 2 | 0.220 | 0.220 | 0.220 |
| worktree-gc-report | 2 | 1.010 | 0.930 | 0.930 |
| zero-collection-tests | 2 | 19.150 | 18.070 | 18.070 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 123.670 | 123.610 | 27 | False | 0 |
| 1 | 0 | 121.350 | 121.290 | 27 | False | 0 |

