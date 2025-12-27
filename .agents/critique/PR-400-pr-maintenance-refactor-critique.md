# Plan Critique: PR Maintenance Workflow Refactoring

**Branch**: `fix/400-pr-maintenance-visibility`
**Review Date**: 2025-12-26
**Reviewer**: critic

## Verdict

**NEEDS REVISION**

## Summary

The PR maintenance workflow refactoring introduces parallel PR processing with matrix strategy, auto-resolution of merge conflicts, and AI-powered conflict analysis. The implementation is mostly sound with strong security controls (ADR-015 compliance) and comprehensive test coverage. However, critical gaps exist in the AI conflict resolution workflow, error handling, and operational validation.

## Strengths

- **Security validation**: ADR-015 compliance in Resolve-PRConflicts.ps1 with branch name and path validation
- **Test coverage**: 266 lines of tests for Resolve-PRConflicts.ps1, 124 unit tests for extracted skill functions
- **Auto-resolvable patterns**: Comprehensive list of auto-resolvable files with clear rationale (`.agents/*`, `.serena/*`, lock files, templates)
- **Matrix parallelization**: Proper use of GitHub Actions matrix strategy to process PRs in parallel (max-parallel: 3)
- **Dual-mode operation**: Script handles both GitHub Actions runner and local worktree environments cleanly
- **Fail-safe design**: Auto-resolution aborts merge when non-auto-resolvable conflicts exist

## Issues Found

### Critical (Must Fix)

- [ ] **Missing .github/actions/ai-review action implementation** (Line 229, pr-maintenance.yml)
  - Workflow references `./.github/actions/ai-review` but action.yml exists without implementation steps
  - Action.yml defines inputs/outputs but no `runs:` section with actual steps
  - This will cause workflow failure when AI conflict analysis is triggered
  - **Evidence**: Read action.yml lines 1-100, no `runs:` section found

- [ ] **AI conflict resolution JSON parsing is fragile** (Lines 256-273, pr-maintenance.yml)
  - Uses regex `\{[\s\S]*"resolutions"[\s\S]*\}` to extract JSON from AI output
  - No validation that extracted JSON is well-formed before ConvertFrom-Json
  - No handling for AI returning markdown code fences around JSON
  - **Risk**: Will fail silently or throw exceptions on malformed AI responses

- [ ] **No verification of AI-resolved conflicts** (Lines 310-316, pr-maintenance.yml)
  - After applying AI resolutions, only checks for remaining conflict markers (`git diff --name-only --diff-filter=U`)
  - Does NOT verify that resolved files are syntactically valid or semantically correct
  - No test suite execution before pushing resolved conflicts
  - **Risk**: Could push broken code that passes merge conflict checks but fails CI

- [ ] **Unhandled edge case: Empty resolutions array** (Lines 269-272, pr-maintenance.yml)
  - Checks `if (-not $resolutions -or -not $resolutions.resolutions)` but does NOT check if `$resolutions.resolutions` is an empty array
  - Foreach loop on line 281 will silently succeed with 0 iterations, leaving conflicts unresolved
  - No error message indicating AI provided empty resolutions
  - **Risk**: Workflow continues without resolving conflicts, misleading success state

### Important (Should Fix)

- [ ] **Incomplete auto-resolvable file patterns** (Lines 75-104, Resolve-PRConflicts.ps1)
  - Pattern `.agents/*` matches `.agents/HANDOFF.md` but also `.agents/architecture/ADR-*.md`
  - ADRs should NOT be auto-resolved (they are critical design decisions)
  - Pattern `.claude/skills/*` is too broad (3 levels deep but skills can be nested deeper)
  - **Recommendation**: Explicitly exclude ADRs, add depth limit validation

- [ ] **Missing retry logic for git push failures** (Lines 357-360, Resolve-PRConflicts.ps1)
  - Git push can fail due to race conditions (another push happened first)
  - Script exits with error instead of fetching, rebasing, and retrying push
  - **Evidence**: Line 359 `throw "Git push failed: $pushOutput"`
  - **Recommendation**: Add retry loop with exponential backoff (3 attempts)

- [ ] **No timeout for AI conflict analysis step** (Lines 226-244, pr-maintenance.yml)
  - `timeout-minutes: 5` set in ai-review action inputs, but no step-level timeout
  - If ai-review action hangs, entire job waits for 30 minutes (job timeout)
  - **Recommendation**: Add step-level `timeout-minutes: 10` to AI analysis step

- [ ] **Prompt file path not validated** (Line 241, pr-maintenance.yml)
  - `prompt-file: .github/prompts/merge-conflict-analysis.md` passed without validation
  - If file missing or malformed, ai-review action will fail with unclear error
  - **Recommendation**: Add step to validate prompt file exists before invoking ai-review

- [ ] **Conflict context preparation assumes git merge succeeds** (Lines 178-224, pr-maintenance.yml)
  - Line 185 `$null = git merge "origin/${{ matrix.baseRefName }}" 2>&1` discards exit code
  - If merge fails for reasons OTHER than conflicts (e.g., binary file issues), script continues
  - No check for `$LASTEXITCODE` to distinguish merge conflict from merge failure
  - **Risk**: Invalid conflict context passed to AI, leading to incorrect resolution strategy

### Minor (Consider)

- [ ] **DryRun mode does not simulate conflict detection** (Lines 285-289, Resolve-PRConflicts.ps1)
  - DryRun returns success immediately without testing conflict detection logic
  - Cannot verify auto-resolvable patterns in dry-run mode
  - **Recommendation**: Add dry-run mode that simulates merge and reports what WOULD be resolved

- [ ] **Missing observability for matrix job failures** (Lines 332-377, pr-maintenance.yml)
  - Summarize job collects results but does NOT distinguish between job failure types
  - No reporting of which PRs failed auto-resolution vs which needed AI vs which succeeded
  - **Recommendation**: Add per-PR status to GITHUB_STEP_SUMMARY

- [ ] **Hardcoded max-parallel value** (Line 134, pr-maintenance.yml)
  - `max-parallel: 3` is fixed, no way to adjust based on rate limit or load
  - Could be input parameter for workflow_dispatch
  - **Recommendation**: Add `max_parallel` workflow input (default: 3)

- [ ] **Test coverage for GitHub runner mode only** (Resolve-PRConflicts.Tests.ps1)
  - Tests validate script syntax and function definitions
  - NO integration tests for actual merge conflict scenarios
  - NO tests for worktree mode (local execution)
  - **Recommendation**: Add integration tests with git test repositories

## Questions for Planner

1. **AI review action missing**: Is `.github/actions/ai-review/action.yml` a work-in-progress or was implementation step missed in this PR?
2. **Conflict resolution verification**: Should AI-resolved PRs trigger CI before pushing, or rely on post-push CI to catch issues?
3. **ADR auto-resolution**: Is accepting target branch version for ADRs intentional? ADRs should be immutable once merged.
4. **Retry strategy**: What is acceptable failure rate for git push retries? Should we block PR or continue with warnings?
5. **Prompt template versioning**: How do we version `.github/prompts/merge-conflict-analysis.md` to ensure AI behavior is reproducible?

## Recommendations

### Immediate Actions (Before Merge)

1. **Complete ai-review action implementation**
   - Add `runs:` section to `.github/actions/ai-review/action.yml`
   - OR remove AI conflict resolution workflow steps until action is ready
   - Document that AI resolution is a planned feature, not active yet

2. **Harden JSON parsing**
   - Extract JSON from markdown code fences (`` ```json ... ``` ``)
   - Validate JSON schema before parsing
   - Add error handling for malformed responses with clear failure messages

3. **Add syntax validation after AI resolution**
   - For PowerShell files: `pwsh -NoProfile -Syntax -File $file`
   - For markdown files: `npx markdownlint-cli2 $file`
   - For JSON files: `ConvertFrom-Json -ErrorAction Stop`
   - Abort merge if validation fails

4. **Fix empty resolutions check**
   - Change line 269 to: `if (-not $resolutions -or -not $resolutions.resolutions -or $resolutions.resolutions.Count -eq 0)`
   - Add explicit error message when AI returns zero resolutions

5. **Exclude ADRs from auto-resolution**
   - Add to line 79: `# Note: .agents/* excludes .agents/architecture/ADR-*.md (handled separately)`
   - Add explicit check before auto-resolving to reject ADR files

### Post-Merge Improvements

1. **Add integration tests**
   - Create test git repository with known conflict scenarios
   - Verify auto-resolution patterns work correctly
   - Test both GitHub runner mode and local worktree mode

2. **Implement retry logic**
   - Wrap git push in retry loop (3 attempts, exponential backoff)
   - Handle race conditions where another push beats us

3. **Add observability**
   - Report per-PR status in GITHUB_STEP_SUMMARY
   - Distinguish auto-resolved, AI-resolved, and failed PRs
   - Include links to workflow runs for each PR

4. **Validate prompt templates on startup**
   - Check that `.github/prompts/merge-conflict-analysis.md` exists
   - Validate it contains required placeholders
   - Fail fast if prompt is malformed

## Acceptance Criteria Validation

**From Issue #400**: Add visibility when 0 PRs processed

- [x] Workflow shows summary when no PRs need action (lines 89-123)
- [x] Discovery step outputs has-prs flag (line 79)
- [x] Summarize job shows final results (lines 332-377)
- [x] Metric counts displayed in table format (lines 100-106)

**Parallel Processing**:

- [x] Matrix strategy configured (lines 125-134)
- [x] PRs processed in parallel (max 3)
- [x] fail-fast disabled (line 133)

**Auto-Resolution**:

- [x] Auto-resolvable files defined (lines 75-104, Resolve-PRConflicts.ps1)
- [x] Security validation implemented (ADR-015)
- [x] Both GitHub runner and local worktree modes supported
- [ ] INCOMPLETE: Test coverage for integration scenarios

**AI Conflict Resolution**:

- [ ] INCOMPLETE: ai-review action missing implementation
- [x] Prompt template created (merge-conflict-analysis.md)
- [x] Conflict context prepared with git blame/log (lines 178-224)
- [ ] INCOMPLETE: JSON parsing fragile, needs hardening
- [ ] INCOMPLETE: No syntax validation after AI resolution

## Approval Conditions

This plan CANNOT be approved until:

1. **ai-review action is completed** - Either implement the action or remove AI resolution steps from workflow
2. **JSON parsing is hardened** - Add proper extraction from markdown fences and schema validation
3. **Syntax validation is added** - Verify resolved files are syntactically valid before pushing
4. **Empty resolutions check is fixed** - Handle case where AI returns zero resolutions
5. **ADR exclusion is clarified** - Confirm whether ADRs should be auto-resolved or excluded

## Escalation Required

**No** - Issues are technical implementation gaps, not conflicting specialist recommendations.

## References

- **Issue**: #400 (PR maintenance visibility)
- **ADR**: ADR-015 (Security validation for git operations)
- **Workflow**: `.github/workflows/pr-maintenance.yml`
- **Script**: `.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1`
- **Prompt**: `.github/prompts/merge-conflict-analysis.md`
- **Tests**: `.claude/skills/merge-resolver/tests/Resolve-PRConflicts.Tests.ps1`

---

**Next Step**: Return to orchestrator with recommendation to route to planner for addressing Critical issues.
