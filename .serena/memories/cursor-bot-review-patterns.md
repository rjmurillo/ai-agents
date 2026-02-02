# cursor[bot] Review Patterns

## Overview

cursor[bot] (Cursor Bugbot) is an AI code reviewer that has demonstrated exceptionally high actionability in PR reviews. Unlike other bots that produce noisy suggestions, cursor[bot] comments consistently identify real bugs.

## Actionability Statistics

| PR | Comments | Actionable | Rate | Notes |
|----|----------|------------|------|-------|
| #32 | 1 | 1 | 100% | Documentation consistency (devops sequence) |
| #47 | 4 | 4 | 100% | PathInfo bugs, test coverage gaps |
| #52 | 5 | 5 | 100% | Git staging, status messages, grep patterns, SKIP_AUTOFIX ignored, PassThru exit codes |
| #212 | 2 | 2 | 100% | Milestone single-item check, null method call on empty results |
| #249 | 8 | 8 | 100% | Hardcoded branch, DryRun bypass, CI blocking, missing env var, exit codes, test drift |
| #249 | 8 | 8 | 100% | Hardcoded branch, DryRun bypass, CI blocking, missing env var, exit codes, test drift |
| **Total** | **28** | **28** | **100%** | All comments identified real bugs |

## Pattern: Bug Detection Focus

cursor[bot] excels at detecting:

### 1. Logic Errors

- Incorrect boolean handling
- Missing edge cases
- Off-by-one errors

### 2. Integration Gaps

- Files not staged properly (PR #52: `git diff --quiet` doesn't detect untracked files)
- State inconsistencies (PR #52: status messages misleading when files already synced)

### 3. Pattern Matching Bugs

- Substring matching false positives (PR #52: `grep -q "True"` matches paths)
- Regex anchoring issues

### 4. Type/API Mismatches

- PowerShell PathInfo vs string types (PR #47)
- Return value mismatches

### 5. Cross-Language Semantics (NEW from PR #52)

- PowerShell `return` in script scope exits with code 0 (PR #52: PassThru exit codes masked)
- Exit code contracts violated at bash-PowerShell boundary

### 6. Pattern Consistency Violations (NEW from PR #52)

- Missing environment variable checks (PR #52: SKIP_AUTOFIX ignored)
- Inconsistent code patterns in same file

### 7. PowerShell Null-Safety Issues (NEW from PR #212)

- `-contains` operator on single strings without array coercion (PR #212: milestone single-item check)
- Null method calls on potentially empty arrays (PR #212: `@($null)` array creation)
- Missing null filtering with `Where-Object { $_ }` pattern

### 8. Fail-Safe vs Fail-Open Logic (NEW from PR #249)

- Empty input variables defaulting to unsafe values (PR #249: scheduled DryRun bypass)
- Missing exit code checks after external commands (PR #249: git push silent failure)
- CI vs local environment behavior differences (PR #249: protected branch blocking)

### 9. Workflow Step Isolation Issues (NEW from PR #249)

- Environment variables not propagating between steps (PR #249: GH_TOKEN missing)
- Hardcoded values instead of parameterized inputs (PR #249: 'main' branch hardcoded)
- Test-implementation drift when parameters change (PR #249: -MinimumRemaining vs $ResourceThresholds)

### 10. Pre-PR Validation Gaps (NEW from PR #249)

- Cross-cutting concerns not tested (branch names, CI environment, env var propagation)
- Fail-safe vs fail-open logic inversions (scheduled triggers bypassing safety)
- Test-implementation synchronization drift (parameter name changes)
- Logging gaps in error paths (rate limit reset time not captured)

## Handling Recommendations

### Priority: HIGH (Trust But Verify)

cursor[bot] comments should be prioritized but verified before implementation:

```python
# Recommended triage for cursor[bot]
if comment.author == "cursor[bot]":
    # High priority - but verify before fixing (sample size n=12, need n=30 for "skip analysis")
    # 1. Read the comment and understand the bug claim
    # 2. Verify the bug exists in the code
    # 3. Then implement fix
    Task(subagent_type="implementer", prompt="Verify and fix if confirmed: [comment summary]...")
```

### Sample Size Limitation

**Current sample**: n=28 comments across 6 PRs (100% actionable)

**Statistical note**: With 28 samples and 0 failures, the 95% confidence interval for true actionability is approximately 88-100%. Approaching "skip analysis" threshold.

**Threshold for "skip analysis"**: When sample reaches n=30 with continued 100% rate, upgrade to skip-analysis handling. Currently at 28/30 (93% to threshold).

### Track Record

As of December 2025, cursor[bot] has produced zero false positives. Every comment has required a code change. However, the first false positive will be blindly implemented if we skip verification.

### Comment Format

cursor[bot] comments include:

- Severity badge (Medium/Low)
- Clear bug description
- Specific line reference
- Often includes suggested fix

Example:

```markdown
### Bug: Newly created mcp.json not staged by pre-commit

<!-- **Medium Severity** -->

The `git diff --quiet` check doesn't detect untracked files...
```

## Comparison with Other Bots

| Bot | Signal Quality | False Positive Rate | Best For |
|-----|----------------|---------------------|----------|
| cursor[bot] | **High (100%)** | 0% | Bug detection |
| Copilot | High | ~10% | Edge cases, type safety |
| CodeRabbit | Medium | ~30-50% | Style, security suggestions |

## Action Items When cursor[bot] Comments

1. **Acknowledge immediately** (👀 reaction)
2. **Implement fix without extensive analysis** (proven track record)
3. **Add regression test** (cursor[bot] bugs often reveal test gaps)
4. **Reply with commit hash** when fixed

## References

- PR #32: Documentation consistency
- PR #47: PathInfo type bug, test coverage
- PR #52: Git staging, status messages, grep patterns
- PR #212: PowerShell null-safety issues (array coercion, null filtering)
- PR #249: Fail-safe logic, CI environment, workflow step isolation (8 bugs, 100% actionable)
- Memory: [pattern-git-hooks-grep-patterns](pattern-git-hooks-grep-patterns.md) (PR #52 specific learnings)
- Memory: [skills-powershell](skills-powershell.md) (Skill-PowerShell-002, 003, 004 from PR #212)
