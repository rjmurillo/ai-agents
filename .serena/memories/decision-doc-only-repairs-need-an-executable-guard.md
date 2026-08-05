# A documentation-only repair with no test does not survive a merge

## Decision

When a repair changes only prose or shell snippets inside an agent carrier, ship an
executable guard in the same PR. Prove the guard by running it against the pre-fix
carriers and recording the failed/passed split in the commit message.

## Why (evidence, measured 2026-08-03)

PR #4277 (`fix(agents): define comment map status vocabulary and unify gate severity`)
merged as `923628a01`. Two repairs that had been validated on its head branch were not
in merged `main` at `fa57eb5cb`:

1. The pr-comment-responder gates read `get_pr_checks.py` output at the envelope top
   level (`.AllPassing`, `.FailedCount`, `.PendingCount`). `write_skill_output` in
   `scripts/github_core/output.py` nests the payload under `Data`, so those reads
   resolve to `null` and the `= "true"` comparison can never pass. This repair had no
   test, so nothing failed when it disappeared.
2. The Comment Map Status Vocabulary section published
   `grep -Ec "Status: \[NEW\]|Status: \[ACKNOWLEDGED\]|Status: pending"`. Maps emit
   `**Status**: [NEW]`, so the pattern matched nothing. This repair did have a test,
   which is how the loss was detectable at all.

The asymmetry is the lesson. Repair 2 was recoverable because a test named it.
Repair 1 was invisible until someone re-read the carrier by hand.

## How to prove a carrier guard actually discriminates

Check the carrier files out at the base SHA with the new test in place, run pytest,
then restore them:

```
git checkout <base-sha> -- <carrier paths>
uv run pytest tests/<new test>.py -q     # must FAIL
git checkout HEAD -- <carrier paths>
uv run pytest tests/<new test>.py -q     # must PASS
```

Measured for the two guards restored in the follow-up branch
`fix/4054-restore-lost-pr-comment-responder-gate-repairs`:

| Guard | Pre-fix carriers | After fix |
|---|---|---|
| `tests/test_pr_comment_responder_status_greps.py` | 18 failed, 5 passed | 23 passed |
| `tests/test_pr_comment_responder_check_envelope.py` | 7 failed, 4 passed | 11 passed |

A guard that passes in both columns is not a guard.

## Related

- ADR-056 defines the envelope; `write_skill_output` is the canonical source.
- Issue #4465 tracks the same top-level-read defect in
  `.claude/skills/github/references/patterns.md`, a different consumer.
- `mem:agents-two-pipeline-mirror-recipe.md` covers which carrier copies must move
  together.
