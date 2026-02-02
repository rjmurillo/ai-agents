# Retrospective: AI Issue Triage Import-Module Failure

**Date**: 2025-12-21
**Incident**: AI Issue Triage workflow runtime failure
**Duration**: ~5 hours (merge to fix)
**Impact**: HIGH - Critical workflow broken, no auto-triage for issues #219, #220
**Root Cause**: PowerShell Import-Module path missing `./` prefix

---

## Executive Summary

PR #212 (security fix) introduced PowerShell Import-Module statements without `./` prefix, causing workflow failures in GitHub Actions. The error was not caught by 51 bot reviews or pre-merge validation. First failure occurred 5 hours post-merge when real issues triggered the workflow.

**Key Insight**: Environment-dependent path resolution issues require integration testing, not just static analysis.

---

## Incident Timeline

| Time | Event | Impact |
|------|-------|--------|
| 2025-12-21 16:30 UTC | PR #212 merged | Security fix deployed |
| ~21:30 UTC (+5h) | Issues #219, #220 created | Workflow triggered |
| ~21:30 UTC | Runs 20416311554, 20416315677 fail | Auto-triage broken |
| ~21:35 UTC | PR #222 created | Fix identified |
| ~21:40 UTC | PR #222 merged | Workflow restored |

**Total Downtime**: ~5 hours (no auto-triage available)

---

## Root Cause Analysis

### Immediate Cause

PowerShell Import-Module requires explicit `./` prefix for relative file paths:

```powershell
# WRONG (PR #212, commit 981ebf7)
Import-Module .github/scripts/AIReviewCommon.psm1

# CORRECT (PR #222)
Import-Module ./.github/scripts/AIReviewCommon.psm1
```

**Error message**: `The specified module '.github/scripts/AIReviewCommon.psm1' was not loaded because no valid module file was found in any module directory.`

### Why PowerShell Behaves This Way

PowerShell distinguishes "module names" from "file paths":

- **Module name** (no path separators): Searched in `$env:PSModulePath`
  - Example: `Import-Module PSScriptAnalyzer`
- **File path** (requires `./` or absolute path): Loaded from file system
  - Example: `Import-Module ./MyModule.psm1`

Without `./`, the argument `.github/scripts/AIReviewCommon.psm1` is ambiguous:
- Contains path separator `/` but no `./` prefix
- PowerShell treats as module name, searches PSModulePath
- Not found in PSModulePath → error

### Contributing Factors

1. **No integration testing**
   - Workflow changes not tested before merge
   - Only syntax validation performed (gh CLI linting)
   - First test was production execution

2. **Bot review limitations**
   - 51 reviews (CodeRabbit, Copilot, Cursor) analyze code
   - Bots don't execute scripts in CI environment
   - Path resolution is runtime behavior, not static

3. **Environment parity gap**
   - Local development may have modules in PSModulePath
   - CI environment (ubuntu-latest) has minimal PSModulePath
   - Error only manifests in CI runtime

4. **Workflow trigger delay**
   - AI Issue Triage triggers on `issues` events only
   - No issues created in 5-hour window post-merge
   - First trigger revealed failure

---

## Impact Analysis

### Severity: HIGH

**Blast Radius**:
- All new issues in 5-hour window (#219, #220)
- Workflow runs: 2 confirmed failures
- User-facing functionality degraded (no auto-triage)

**Business Impact**:
- Manual triage required for affected issues
- Delayed categorization and milestone assignment
- Reduced developer productivity (manual labeling)

**Technical Debt**:
- No workflow integration tests (gap identified)
- Pre-commit validation insufficient
- Documentation missing PowerShell CI best practices

---

## What Went Wrong

### 1. Review Process Gaps

**51 bot reviews** didn't catch runtime error because:
- Bots analyze code statically (AST, linting)
- Don't execute in CI environment
- Path resolution is environment-dependent behavior

**Human review** didn't catch it because:
- Syntax appears valid (IS valid PowerShell)
- Error only occurs in specific execution context
- Reviewer likely not PowerShell CI expert

### 2. Testing Gaps

**No integration tests** for workflows:
- Syntax validation only (`gh workflow view`)
- No dry-run with test data
- No module import validation in CI

**Pre-commit hooks** insufficient:
- PSScriptAnalyzer doesn't flag missing `./` prefix
- No custom rule for Import-Module paths
- Static analysis doesn't catch runtime context

### 3. Deployment Gaps

**No canary/staged rollout**:
- Workflow changes deploy immediately on merge
- No test environment or dry-run validation
- First execution is production

**No monitoring**:
- Workflow failures not immediately visible
- No alerts for failed runs
- Discovery via manual inspection or user report

---

## What Went Right

### Rapid Response

**Fix turnaround**: ~10 minutes from failure discovery to PR #222 merge
- Issue identified quickly (clear error message)
- Root cause obvious (Import-Module path)
- Fix simple (add `./` prefix)

### Security Posture Improved

**PR #212 still valuable**:
- Replaced bash parsing with PowerShell (CWE-20/CWE-78 remediation)
- Hardened regex prevents command injection
- Import-Module bug doesn't negate security value

### Documentation & Learning

**Retrospective value**:
- Skills extracted (Skill-PowerShell-005, Skill-CI-Integration-Test-001)
- Pattern documented for future reference
- Institutional knowledge captured

---

## Skills Extracted

### Skill-PowerShell-005: Import-Module Relative Path Prefix (98%)

**Statement**: Always prefix relative file paths with `./` in PowerShell Import-Module commands

**Pattern**:
```powershell
# CORRECT
Import-Module ./path/to/module.psm1

# WRONG
Import-Module path/to/module.psm1
```

**Why**: PowerShell treats arguments without `./` as module names, searches PSModulePath only. CI environments have minimal PSModulePath.

**Atomicity**: 98%
**Impact**: 9/10

### Skill-CI-Integration-Test-001: Workflow Integration Testing (88%)

**Statement**: Test GitHub Actions workflows in dry-run mode or separate test environment before merging changes

**Pattern**: Add workflow validation job that tests module imports, script execution, and dry-run workflows

**Why**: Static analysis doesn't catch runtime errors. Environment-specific issues (paths, modules, auth) require execution tests.

**Atomicity**: 88%
**Impact**: 8/10

---

## Recommendations

### Immediate Actions (P0)

1. **Add workflow validation CI** ✅
   - Test PowerShell module imports on PR
   - Validate workflow syntax
   - Dry-run workflows with test data
   - **Owner**: DevOps team
   - **Timeline**: Next sprint

2. **Pre-commit hook enhancement** ✅
   - Check Import-Module paths have `./` prefix
   - Custom PSScriptAnalyzer rule
   - **Owner**: DevOps team
   - **Timeline**: Next sprint

### Short-term Improvements (P1)

3. **Workflow testing framework**
   - Automated dry-run on workflow changes
   - Test issue/PR event simulation
   - Environment parity validation
   - **Owner**: DevOps team
   - **Timeline**: Q1 2026

4. **Bot review enhancement**
   - Configure CodeRabbit/Copilot to flag Import-Module without `./`
   - Add custom linting rules for workflow scripts
   - **Owner**: Platform team
   - **Timeline**: Q1 2026

### Long-term Initiatives (P2)

5. **Canary deployment for workflows**
   - Test environment for workflow changes
   - Staged rollout (test → prod)
   - Monitoring and alerting
   - **Owner**: Platform team
   - **Timeline**: Q2 2026

6. **Documentation**
   - PowerShell CI/CD best practices guide
   - Workflow testing guidelines
   - Common pitfalls (path resolution, module loading)
   - **Owner**: Documentation team
   - **Timeline**: Q1 2026

---

## Lessons Learned

### 1. Bot Reviews Are Not Execution Tests

**Insight**: 51 bot reviews analyzed code but didn't execute in CI environment.

**Action**: Add integration tests that execute workflows, not just analyze syntax.

### 2. Static Analysis Has Limits

**Insight**: PSScriptAnalyzer and syntax validators don't catch environment-dependent runtime errors.

**Action**: Supplement static analysis with execution tests in CI-like environments.

### 3. Workflows Are Production Code

**Insight**: Workflows deploy immediately on merge without testing, unlike application code.

**Action**: Treat workflows as production code - require integration tests before merge.

### 4. Environment Parity Matters

**Insight**: Local development (PSModulePath populated) differs from CI (minimal PSModulePath).

**Action**: Test scripts in CI-like environment before commit (Skill-CI-Environment-Testing-001).

### 5. Common Mistakes Deserve Skills

**Insight**: Import-Module path prefix is common PowerShell CI pitfall.

**Action**: Document as skill (Skill-PowerShell-005) and add to review checklist.

---

## Conclusion

This incident reveals **testing gaps** in workflow deployment process. While bot reviews provide value (security analysis, style checks), they don't replace **integration testing** in CI environments.

**Key Takeaway**: Environment-dependent behaviors (path resolution, module loading, auth) require **execution tests**, not just static analysis.

**Positive Outcome**: Skills extracted, gaps identified, recommendations actionable. PR #212 security value preserved despite runtime bug.

**Atomicity Score**: Both skills scored 88-98% atomicity - highly specific, actionable patterns.

---

## Appendix: Failure Pattern Signature

**Failure Mode**: Environment-Dependent Path Resolution

**Signature**:
1. Code works locally (or not tested locally)
2. Code fails in CI with "module not found" or similar path error
3. Path looks correct but missing environment-specific prefix (`./`)
4. Bot reviews don't catch it (no execution)
5. First test is production execution

**Detection**:
- Pre-commit: PowerShell linting with path validation
- CI: Workflow dry-run or integration test
- Code review: Human reviewer with PowerShell CI experience

**Prevention**:
- Always use `./` for relative file paths in Import-Module
- Test PowerShell scripts in CI-like environment before commit
- Add workflow validation to CI pipeline

**Related Patterns**:
- Skill-CI-Environment-Testing-001: Local CI simulation
- Skill-CI-001: Pre-commit syntax validation
- Skill-PowerShell-005: Import-Module relative path prefix

---

## References

- **PR #212**: fix(security): remediate CWE-20/CWE-78 in ai-issue-triage workflow
- **PR #222**: fix(workflow): add missing ./ prefix to Import-Module paths
- **Commit**: 981ebf7 (introduced bug)
- **Failing Runs**: 20416311554, 20416315677
- **Affected Issues**: #219, #220
- **Session Log**: `.agents/sessions/2025-12-21-session-56-ai-triage-retrospective.md`
- **Skills Updated**: `skills-powershell`, `skills-ci-infrastructure`
