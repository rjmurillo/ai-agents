# Skill: The taste baseline slack ceiling is enforced by pytest, not by the ratchet (SUPERSEDED)

> **SUPERSEDED 2026-09-16.** The title claim is no longer true. `run()` now calls
> `baseline_health` directly, so the CLI enforces the ceiling itself. Verified at
> `origin/main` `659097d6d`:
>
> ```text
> scripts/ci/count_ratchet.py:385   MAX_BASELINE_SLACK = 6
> scripts/ci/count_ratchet.py:407   def baseline_health(...)
> scripts/ci/count_ratchet.py:1023  problem = baseline_health(count, baseline)   <- PRODUCTION CALLER
> ```
>
> Read the current behavior section below. The 2026-08-05 analysis is kept because
> its generalization still holds and because the line numbers show how far the file
> moved, but do not follow its Recipe: it will send you looking for a clean ratchet
> that is not clean.

## Current behavior (2026-09-16, `659097d6d`)

`run()` has four outcomes, not two:

| Condition | Behavior |
|---|---|
| `count > baseline` | `EXIT_REGRESSION`, always, checked before `--update` is inspected |
| `count < baseline` with `--update` | rewrites the baseline, `EXIT_OK` |
| `count < baseline` without `--update`, slack over 6 | `STALE BASELINE`, `EXIT_REGRESSION` |
| `count < baseline` without `--update`, slack 6 or under | `OK ... slack`, `EXIT_OK` |
| `count == baseline` | `OK`, `EXIT_OK` |

Two consequences the superseded text gets backwards:

1. **A red taste ratchet can mean drift, not a regression.** The ratchet itself
   prints `STALE BASELINE` now. Diagnosing by ratchet output does work.
2. **`--update` cannot absorb an increase.** The write path is reachable only
   inside the `count < baseline` branch. A branch that adds violations fails and
   `--update` will not rescue it.

`tests/ci/test_count_ratchet_against_real_git.py::test_the_shipped_baseline_describes_the_tracked_tree`
still exists and calls the same function, so both paths enforce the same rule.

## Why this matters for a cohort of PRs

The scalar is shared. Measured 2026-09-16 at `ba2a001b7`: baseline 558, true count
558, so slack was exactly 0. Five open issues (#5585, #5586, #5587, #5588, #5599)
each lower it, by 10, 1, 1, 1 and 2 respectively. #5585 alone breaches the ceiling.
The other four sum to 5 and can breach it jointly if two or more land in the same
window without running `--update`.

The remedy that survives merge order is to never write a literal. Capture the
value, measure the issue's own contribution live, run `--update` in the same
commit, then assert the captured delta:

```bash
BASELINE_BEFORE=$(cat scripts/ci/taste_count_baseline.txt)
CONTRIBUTION=$(uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py \
  --format json -- <this change's files> \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['error_count'])")
uv run --frozen python scripts/ci/taste_count_ratchet.py --update
test "$(cat scripts/ci/taste_count_baseline.txt)" -eq "$((BASELINE_BEFORE - CONTRIBUTION))"
```

## Historical analysis (2026-08-05, accurate for that tree only)

At that time `baseline_health` was defined at `count_ratchet.py:206`, the runtime
path was `:447-478`, and every caller was a test. The docstring of the pinning test
recorded two outages on 2026-08-03 at baselines 595 and 593. Issue #4608 tracked the
merge-queue arithmetic: for `n` PRs each lowering the true count by `d` while writing
the same baseline, combined slack is `(n-1) * d`, failing above 6.

## Generalization (still correct, and it is why this file was wrong)

A threshold constant is not a gate. Before trusting any constant to bound behavior,
list its callers and check that at least one runs in production.

The second half is new: **a caller list is a measurement, and measurements expire.**
This memory recorded a true caller list, at 98 percent confidence, and the file grew
by roughly 500 lines underneath it. Nothing re-checked it for six weeks. When a
memory's claim rests on a line number or a caller set, write the command that
reproduces it, and re-run that command before acting on the claim.
