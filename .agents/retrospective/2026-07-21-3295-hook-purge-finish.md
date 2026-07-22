# Retrospective: #3295 vendored-hook purge, false-blocker stop

Date: 2026-07-21
Issue: #3295 (epic #3197)
Branch: `chore/3295-purge-internal-hooks`
Final code commit: `5828139b`

## Failure mode classification

Primary: Failure Mode #3, Ambiguous Instruction Inversion (`.agents/governance/FAILURE-MODES.md`).
Secondary: Failure Mode #4, False Completion Markers (the "Blocked" self-report was inaccurate).

## Summary

A delegated subagent (gpt-5.6-sol) completed the #3295 internal-hook purge correctly:
16 hooks deleted, 2 enforcement gates re-homed into the shared git-hook policy with
positive, negative, and edge tests, plugin manifests bumped to 0.6.98 at parity,
13,428 tests passing, and `pre_pr.py` green. It then stopped and reported
"Blocked. No push or PR was created" because `uv run ruff check .` returned exit 1
with 361 findings. Those 361 findings are pre-existing on origin/main (the #2993
repo-wide condition); zero are in branch-modified files. No hook or gate rejected a
push; no push was ever attempted.

## Root cause (five whys)

1. Why did work stop? The subagent reported a blocker.
2. Why a blocker? `ruff check .` exited 1.
3. Why did exit 1 stop it? The delegation prompt listed "full Ruff" as a Phase 3
   validation step; the agent treated any non-zero exit as blocking.
4. Why was ruff non-zero? 361 pre-existing repo-wide findings (#2993), none in the
   changed files.
5. Why were they not excluded? The instruction said "full Ruff" without scoping it to
   changed files or acknowledging the pre-existing baseline. Ambiguous scope inverted
   into a stop condition.

## Impact

| Area        | Severity | Detail                                                                 |
|-------------|----------|------------------------------------------------------------------------|
| Correctness | Low      | The work was sound. No defective change shipped.                       |
| Throughput  | Medium   | 26 commits of correct work sat unpushed pending human review.          |
| Process     | Medium   | No shared definition of "ruff clean" (changed-files vs repo-wide).     |

## What went right

- The subagent blocked rather than forcing past a perceived gate. The failure was
  scope interpretation, not recklessness.
- The re-homed retrospective gate then correctly blocked the orchestrator's own push
  for missing retrospective evidence. The gate this PR ships enforced on the same repo
  that ships it. Dogfooding worked as designed.

## Remediation

1. Delegation prompts that name a lint gate MUST scope it: "ruff on changed files must
   be clean; repo-wide pre-existing findings (#2993) are not a blocker." Owner:
   orchestrator prompt template.
2. The commit-ceiling (20, ADR-008) versus atomic-commit (5 files) tension for bulk
   purges is resolved by the staged-push plus `commit-limit-bypass` label flow. Recorded
   here so the next bulk purge does not rediscover it. Evidence:
   `check_pr_bypass_label.py`, and the `_check_commit_limit` helper in
   `scripts/validation/git_hook_policy.py`.
3. Store a repository memory so future sessions recognize the #2993 false-blocker
   pattern immediately.

## Evidence

- Issue #3295, epic #3197.
- Pre-existing repo-wide ruff condition: #2993.
- Authorities: ADR-084 (vendored-hook ROI bar), ADR-085 (cross-harness permission
  asymmetry, keep/kill decisions).
