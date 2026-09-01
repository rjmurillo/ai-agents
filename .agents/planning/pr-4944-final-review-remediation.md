# PR #4944 Final Review Remediation

Implementation is merged; this plan governs post-merge evidence repair only.

## Scope
- Correct sessions 14696 and 14697 so lint evidence distinguishes zero eligible session-end selection from explicit artifact Markdown lint.
- Mark this plan's completed acceptance criteria verified.
- Preserve the fresh post-merge review's PASS findings for product code, nested coverage, memory wording, Failure Mode 4 mapping, and the runtime helper.

## File Boundaries
- Start from exact `origin/main` at `e52604fd07c02c71475a5d8e282ba2bd3163516e`, which contains merge commit `5acc676414b423d8a9e10bfe3041ab3ffd284874`.
- Allow only this plan, sessions 14696/14697, validator-required QA reports, and hook-generated matching episodes.
- Do not modify implementation, tests, runtime helpers, retrospective content, memories, `HANDOFF.md`, workflows, historical session 14695 evidence, or unrelated files.

## Ordered Verification and Closure Steps
1. Restore only the four named source artifacts from `91796736cc2f355de354bf473fd8a600b69e1729`.
2. Correct the two evidence findings and run explicit lint on the plan, retrospective, and relevant QA Markdown.
3. Commit initial evidence, rerun focused pytest, Ruff, helper diff, session validators, and branch session policy at that commit.
4. Bind required QA/session evidence to the tested commit, run session-end, and commit generated matching episodes.
5. Run full `pre_pr.py`, final diff checks, path-boundary checks, and product/test/runtime identity checks.

## Acceptance Criteria
- [x] Nested cache directories and `.pyc`/`.pyo` artifacts are recursively excluded.
- [x] The exact root assertion remains `{"module.py"}` and passes.
- [x] Session 14696 retains its truthful no-new-memory evidence.
- [x] The retrospective names `4. False completion markers` and assigns prevention owners.
- [x] Focused integration/E2E pytest and Ruff checks pass.
- [x] The fresh post-merge review found no product, test, runtime, memory, or retrospective defect.
- [x] Both actionable evidence findings are corrected with explicit artifact lint evidence.
- [x] PR #4944 is merged as `5acc676414b423d8a9e10bfe3041ab3ffd284874`.
- [x] `git merge-base --is-ancestor 5acc676414b423d8a9e10bfe3041ab3ffd284874 origin/main` exits 0.
