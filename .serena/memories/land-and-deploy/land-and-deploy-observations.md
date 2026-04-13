# Skill Observations: land-and-deploy

**Last Updated**: 2026-04-13
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from using the `land-and-deploy` skill across sessions. The skill picks up where `/ship` leaves off: merges the PR, waits for deploy, verifies production health, and offers revert as an escape hatch.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- **Never use `Fixes #N` / `Closes #N` / `Resolves #N` on an Epic or parent issue in the PR body merged via this skill.** GitHub's closing-keyword parser auto-closes the Epic on merge regardless of any qualifier text. See `github-observations.md` for full context. Always verify that only the intended sub-issue closes; immediately reopen the Epic with an explanatory comment if it auto-closes. (Session 2026-04-13, PR #1633)
  - Evidence: PR #1633 body contained "Fixes #1574 M0" intending to close only M0 #1623. On squash merge, both M0 AND the Epic #1574 closed. Had to manually reopen the Epic.

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- **For non-gstack projects, skip gstack-specific steps pragmatically.** The skill is designed for repos instrumented with `bin/test-lane`, VERSION 4-digit bumps, CHANGELOG.md at root, TODOS.md, and deploy platforms. On repos without that infrastructure (e.g., ai-agents), skip Step 3 (`bin/test-lane`), Step 4 (VERSION bump), most of Step 5.5 (TODOS auto-update), and Step 6 (deploy platform detection). The core value — merge + review gate + revert escape hatch — still applies. Note the skipped steps in the final report. (Session 2026-04-13, PR #1633)
- **For docs-only PRs, skip the deploy verification chain entirely.** Per the skill's own Step 5 decision tree, when `SCOPE_DOCS` is the only true scope, go directly from Step 4 (merge) to Step 9 (deploy report) with verdict `DEPLOYED (DOCS ONLY — NO SITE TO VERIFY)`. Don't ask about production URLs, don't poll deploy workflows, don't run canary. (Session 2026-04-13, PR #1633)
- **For long async CI queues (agent reviews), use `ScheduleWakeup` between polls instead of sleep loops.** A single `/land-and-deploy` run may need 3-5 polling cycles with 3-5 min waits each when the repo dispatches LLM-based agent reviews (Security/QA/Analyst/Architect/DevOps/Roadmap). Each wakeup cycle re-checks state via GitHub API and resumes at the right step. (Session 2026-04-13, PR #1633)
  - Evidence: PR #1633 needed 4 wakeup cycles over ~15 minutes to wait for 16 required checks across 4 commits to converge.

## Edge Cases (MED confidence)

These are scenarios to handle:

- **`mergeStateStatus: BLOCKED` despite 16/16 required checks green** indicates unresolved review threads per `required_review_thread_resolution` ruleset. Fetch ALL review threads via GraphQL, filter `not isResolved` (NOT `not isResolved and not isOutdated`), and explicitly call `resolveReviewThread` mutation on each. Outdated ≠ resolved. (Session 2026-04-13, PR #1633)
  - Evidence: My initial thread sweep used `not isResolved and not isOutdated` filter and returned 0 matches. User reported "Merging is blocked — A conversation must be resolved." Full sweep found 9 outdated-but-not-resolved threads. After explicit resolve of all 9, mergeStateStatus flipped to CLEAN.
- **Repo rulesets can enforce checks that don't show as "branch protection".** `gh api repos/.../branches/main/protection` returns 404 "Branch not protected" even when `gh api repos/.../rulesets/{id}` contains `required_status_checks`, `required_review_thread_resolution`, etc. Always check both protection AND rulesets when diagnosing BLOCKED merge state. (Session 2026-04-13)
- **Merge via raw `gh pr merge` is blocked by the invoke-skill-first guard hook.** Must use `.claude/skills/github/scripts/pr/merge_pr.py` via `uv run --with pyyaml python ...` (the script imports `yaml` and the scripts package lives at `scripts.github_core` requiring `PYTHONPATH=.`). Arg name is `--pull-request` not `--pr`, and `--strategy squash` not `--method squash`. (Session 2026-04-13, PR #1633)
- **The skill's `gh sub-issue` and similar sub-commands use different flag conventions than parent `gh` commands.** Sub-issue extension uses `--body STRING` not `--body-file FILE`. Test CLI extensions before batching operations. (Session 2026-04-13)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

- For Python skill scripts that depend on `yaml` and `scripts.github_core`, invoking via `uv run --with pyyaml python SCRIPT` works but recreates the venv per-invocation (slow). Consider pre-installing the dev extras or adding pyyaml to `pyproject.toml`'s base deps to speed up skill script calls during merge workflows. (Session 2026-04-13)
- Wakeup-based polling patterns work well for skills that wait on external async state (CI, merge queues, deploy workflows). The pattern: detect current state → if not ready, schedule wakeup 2-5 min out with the same slash command → on wakeup, re-detect and either proceed or re-schedule. (Session 2026-04-13)

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-04-13 | PR #1633 incident | HIGH | Fixes keyword on Epic auto-closes it; immediately reopen with explanation |
| 2026-04-13 | PR #1633 | MED | Skip gstack-specific steps on non-gstack repos; core value is merge + review gate + revert |
| 2026-04-13 | PR #1633 | MED | Docs-only PRs skip Steps 5-7 deploy verification chain entirely |
| 2026-04-13 | PR #1633 | MED | Use ScheduleWakeup between polls for async agent review queues |
| 2026-04-13 | PR #1633 | MED | BLOCKED merge state with 16/16 checks = unresolved (not merely outdated) threads |
| 2026-04-13 | PR #1633 | MED | Rulesets enforce checks that don't show as branch protection; check both |
| 2026-04-13 | PR #1633 | MED | merge_pr.py requires uv run + PYTHONPATH + --pull-request + --strategy flag names |
| 2026-04-13 | PR #1633 | MED | `gh sub-issue create` uses --body STRING not --body-file |
| 2026-04-13 | PR #1633 | LOW | uv venv re-creation per Python skill invocation is slow; pre-install deps |
| 2026-04-13 | PR #1633 | LOW | Wakeup polling pattern for async CI state is effective |

## Related

- [github-observations](../github/github-observations.md) — GitHub API patterns, closing-keyword gotcha
- [pr-review-observations](../pr-review/pr-review-observations.md) — review thread resolution, bot reviewer behavior
- [session-protocol-observations](../session/session-protocol-observations.md) — wakeup scheduling patterns
