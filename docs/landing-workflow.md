# Serial Auto-Merge Landing Workflow

## Overview

This repository uses serial one-front GitHub squash auto-merge. Exactly one PR
is updated and tested at a time. There is no native merge queue (user-owned
repositories are ineligible).

## Live configuration (measured 2026-08-15)

| Setting | Value | Source |
|---------|-------|--------|
| Ruleset | 11104075 ("Copilot review for default branch") | `gh api repos/rjmurillo/ai-agents/rulesets` |
| `strict_required_status_checks_policy` | `false` | `gh api repos/rjmurillo/ai-agents/rules/branches/main` |
| Allowed merge methods | squash only | ruleset `pull_request.allowed_merge_methods` |
| Required thread resolution | true | ruleset `pull_request.required_review_thread_resolution` |
| Required approving reviews | 0 | ruleset `pull_request.required_approving_review_count` |
| Required linear history | true | ruleset `required_linear_history` |
| Merge queue | none (user-owned repo ineligible) | GitHub limitation |

## Why serial landing

Updating 41 behind branches in parallel triggered 820 queued workflow runs. The
first merge invalidated the other 40 matrices. Auto-merge was disabled on 41
PRs and 818 runs were cancelled. The protocol now updates only the front PR.

## Landing sequence

```text
1. Select the front PR (highest priority or oldest green).
2. Merge origin/main into the PR branch (or rebase).
3. Wait for all 16 required status checks to pass.
4. Arm squash auto-merge (or merge manually).
5. After merge, verify main push workflows are green.
6. Advance to the next PR. Repeat from step 2.
```

## Stale recalculation

Each merge to main changes the tree. Open PRs become stale because:

- **Count ratchets** compare the branch baseline against main. If main lowered
  a baseline, every branch recording the old value fails until it picks up the
  new one.
- **Corpus claims** (always-on rule figures) go stale when main changes rule
  sizes.
- **Required checks** ran against an older main. Even with `strict: false`, the
  count ratchets enforce effective freshness.

### Recovery procedure

```bash
git fetch origin main
git merge origin/main --no-edit

# Verify all ratchets pass locally before pushing:
for r in taste_count_ratchet ruff_count_ratchet; do
  uv run --frozen python scripts/ci/${r}.py --base-ref origin/main
done

# If a ratchet fires on inherited violations (not your changes):
# 1. Check RUF100 (dead noqa) first: provably safe to remove.
# 2. Lower the baseline only if main already lowered it.
# 3. Never raise a baseline to absorb a regression.
```

## Cost model

With N open PRs and R required checks per PR, parallel refresh costs O(N *R)
runs per landing. Serial one-front costs O(R) per landing, O(N* R) total for
the full queue. The per-landing cost is fixed; queue depth determines total
wall time.

## Strict policy status

As of 2026-08-15, `strict_required_status_checks_policy` is `false` on ruleset
11104075. The count ratchets still enforce effective branch freshness because
they compare against the base ref tree, so a branch behind main fails CI even
though GitHub does not block the merge button. The operational effect is the
same: merge main before pushing.

Historical note: strict was set to `true` between 2026-08-04 and some point
before 2026-08-15. The serial one-front workflow is independent of this
setting; it controls CI cost regardless of whether GitHub or the ratchets
enforce freshness.

## Governance

- Auto-merge is prohibited for PRs changing `.agents/governance/**` (requires
  human maintainer approval).
- Dependent new work uses stacked PRs. Unrelated backlog work must not be
  stacked.
- After merging a batch, run the suite against main before declaring the sweep
  done. Per-PR green does not compose.
