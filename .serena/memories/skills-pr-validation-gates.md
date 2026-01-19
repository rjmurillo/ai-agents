# Skills: PR Validation Gates

## Overview

Skills extracted from PR #249 retrospective (Session 72). These represent quality gates that should prevent P0-P1 issues from reaching PR stage.

## Skill-PR-249-001: Scheduled Workflow Fail-Safe Default

**Statement**: When workflow inputs are empty (scheduled triggers), default to fail-safe mode (dry_run=true)

**Context**: GitHub Actions scheduled workflows don't populate `inputs.*` variables

**Evidence**: PR #249 P0-2 - scheduled runs bypassed DryRun safety

**Atomicity**: 96%

**Pattern**:

```yaml
- name: Set DryRun Mode
  run: |
    inputValue="${{ inputs.dry_run }}"
    if [ -z "$inputValue" ] || [ "$inputValue" = "true" ]; then
      echo "DRY_RUN=true" >> $GITHUB_ENV
    else
      echo "DRY_RUN=false" >> $GITHUB_ENV
    fi
```

**Pre-PR Validation**:

- [ ] All boolean inputs have explicit default in workflow_dispatch
- [ ] Empty input handling tested for scheduled triggers
- [ ] Fail-safe mode is ON when input missing

---

## Skill-PR-249-002: PowerShell LASTEXITCODE Check Pattern

**Statement**: After any external command (git, gh), check $LASTEXITCODE before proceeding

**Context**: PowerShell doesn't throw on non-zero exit codes from external commands

**Evidence**: PR #249 P1-4 - git push failures silently ignored

**Atomicity**: 94%

**Pattern**:

```powershell
git push origin $BranchName 2>&1 | Write-Verbose
if ($LASTEXITCODE -ne 0) {
    throw "git push failed with exit code $LASTEXITCODE"
}
```

**Pre-PR Validation**:

- [ ] Every `git` command followed by LASTEXITCODE check
- [ ] Every `gh` command followed by LASTEXITCODE check
- [ ] Error message includes exit code for debugging

---

## Skill-PR-249-003: CI Environment Detection

**Statement**: Detect CI environment (GITHUB_ACTIONS=true) for behavior variations

**Context**: Operations valid in CI may differ from local execution

**Evidence**: PR #249 P0-3 - protected branch check incorrectly blocked CI

**Atomicity**: 92%

**Pattern**:

```powershell
if ($env:GITHUB_ACTIONS -eq 'true') {
    Write-Verbose "Running in CI environment - allowing operation"
    return $true
}
```

**Pre-PR Validation**:

- [ ] Scripts tested in BOTH local and CI contexts
- [ ] CI-specific behavior documented in comments
- [ ] Environment detection uses standard variable ($env:GITHUB_ACTIONS)

---

## Skill-PR-249-004: Workflow Step Environment Propagation

**Statement**: Explicitly declare env vars in each workflow step that needs them

**Context**: GitHub Actions don't inherit job-level secrets to step-level automatically

**Evidence**: PR #249 P1-1 - summary step missing GH_TOKEN

**Atomicity**: 95%

**Pattern**:

```yaml
- name: Generate Summary
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    gh api rate_limit ...
```

**Pre-PR Validation**:

- [ ] Every step using `gh` CLI has GH_TOKEN env
- [ ] Every step using GitHub API has required auth
- [ ] Env vars not assumed from previous steps

---

## Skill-PR-249-005: Parameterize Branch References

**Statement**: Never hardcode branch names; pass as parameter or read from PR metadata

**Context**: PRs may target branches other than main

**Evidence**: PR #249 P0-1 - hardcoded 'main' in Resolve-PRConflicts

**Atomicity**: 97%

**Pattern**:

```powershell
param(
    [string]$TargetBranch = $pr.baseRefName
)
# Use $TargetBranch instead of 'main'
```

**Pre-PR Validation**:

- [ ] No string literal 'main' or 'master' in merge/rebase code
- [ ] Branch names from PR metadata ($pr.base, baseRefName)
- [ ] Tests include non-main target branch scenarios

---

## Pre-PR Checklist Template

Based on PR #249 root causes, validate before opening PR:

### Cross-Cutting Concerns

- [ ] Tested in CI environment (GITHUB_ACTIONS=true)
- [ ] Tested with non-main target branches
- [ ] All workflow steps have required secrets/env vars
- [ ] Empty input scenarios tested (scheduled triggers)

### Fail-Safe Patterns

- [ ] Safety modes default to ON when input empty/missing
- [ ] All external command exit codes explicitly checked
- [ ] Error states fail closed, not open

### Test-Implementation Sync

- [ ] Tests match current function signatures
- [ ] Parameter names consistent between test and implementation
- [ ] Mock data structures match actual API responses

### Logging/Observability

- [ ] Rate limit reset times captured for scheduling
- [ ] Error messages include diagnostic information
- [ ] Verbose mode shows meaningful progress

## Statistics

**Source**: PR #249 Retrospective (Session 72)
**P0-P1 Issues Prevented**: 7 if checklist followed
**Estimated Time Saved**: 10 hours PR review cycle
**Last Updated**: 2025-12-22

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-agent-workflow-phase3](skills-agent-workflow-phase3.md)
- [skills-agent-workflows](skills-agent-workflows.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-analysis](skills-analysis.md)
