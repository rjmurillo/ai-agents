# CI Workflow Required Checks

## Skill-CI-Workflow-001: Path Filter Anti-Pattern (95%)

**Statement**: Remove path filters from required check workflows; use internal git diff for selective validation

**Context**: When creating GitHub Actions workflow that is a required status check. Path filters at trigger level prevent workflow from running entirely, causing phantom "waiting for status" blocking.

**Evidence**: PR #342 (path filters) didn't fix phantom check; PR #343 (removed filters, internal skip) resolved blocking

**Pattern**:

```yaml
# WRONG: Path filters on required check
on:
  pull_request:
    paths:
      - '.serena/memories/**'  # Workflow won't run if paths don't match

# CORRECT: Always run, skip internally
on:
  pull_request:
    branches:
      - main

jobs:
  validate:
    steps:
      - name: Check for changes
        run: |
          # Internal git diff to detect relevant changes
          if (no changes to .serena/memories/) {
            echo "skip=true"
          }
      - name: Validate
        if: steps.check.outputs.skip != 'true'
        run: ./validate.ps1
```

**Why**: Required checks must report a status. Path filters prevent workflow from running = no status = phantom blocking.

---

## Skill-CI-Workflow-002a: Zero SHA Handling (95%)

**Statement**: Handle zero SHA in workflow git diff by falling back to origin/main comparison

**Context**: When writing workflow change detection using `github.event.before`. First commit on new branch has before SHA of all zeros (0000000...).

**Evidence**: PR #343 lines 62-65: `if ($beforeSha -eq $zeroSha) fallback to origin/main`

**Pattern**:

```powershell
$beforeSha = '${{ github.event.before }}'
$zeroSha = '0000000000000000000000000000000000000000'

if ($beforeSha -eq $zeroSha) {
  Write-Host "First commit on branch detected. Comparing against origin/main..."
  $diffOutput = git diff --name-only origin/main..${{ github.sha }}
} else {
  $diffOutput = git diff --name-only $beforeSha..${{ github.sha }}
}
```

---

## Skill-CI-Workflow-002b: Missing Commit Handling (93%)

**Statement**: Verify commit existence with git cat-file before git diff to handle force-push

**Context**: When using `github.event.before` in workflow git diff. Force-push or rebase can make before commit unavailable in repository.

**Evidence**: PR #343 lines 68-71: `git cat-file -e` check before diff, fallback to main if missing

**Pattern**:

```powershell
$beforeSha = '${{ github.event.before }}'

# Check if commit exists
git cat-file -e "$beforeSha^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Warning: Base commit $beforeSha not found (possible force-push). Falling back to origin/main..."
  $diffOutput = git diff --name-only origin/main..${{ github.sha }}
} else {
  $diffOutput = git diff --name-only $beforeSha..${{ github.sha }}
}
```

---

## Skill-CI-Workflow-002c: Git Diff Exit Code Validation (92%)

**Statement**: Check LASTEXITCODE after git diff before processing output to catch command failures

**Context**: When running git diff in PowerShell workflow step. Git diff can fail silently without proper exit code checking.

**Evidence**: PR #343 lines 83-86: `if ($LASTEXITCODE -ne 0) exit with error`

**Pattern**:

```powershell
$diffOutput = git diff --name-only origin/main...HEAD

# Validate command succeeded
if ($LASTEXITCODE -ne 0) {
  Write-Error "git diff command failed with exit code $LASTEXITCODE"
  exit $LASTEXITCODE
}

# Safe to process output now
$changedFiles = $diffOutput -split '\r?\n' | Where-Object { $_ }
```

---

## Skill-CI-Workflow-003: Required Check Testing (90%)

**Statement**: Test required check workflow with non-matching PR before merge to verify status reporting

**Context**: Before merging required check workflow to main. Phantom check blocking happens when workflow doesn't run but is required.

**Evidence**: PR #342 merged without testing non-memory PR; phantom check persisted until PR #343

**Checklist**:

1. Merge required check workflow to main
2. Create test PR that does NOT match intended validation scope
3. Verify workflow runs and reports status (even if skipped)
4. Check PR shows "Check: passed" not "Waiting for status"
5. If phantom check appears, investigate trigger conditions

**Example**: For memory validation workflow, test with PR that only changes `.github/workflows/` (no `.serena/memories/` files)

---

## Related Files

- [ci-deployment-validation](ci-deployment-validation.md) - Pre-deployment validation patterns
- [ci-quality-gates](ci-quality-gates.md) - Required check configuration
- [workflow-shell-safety](workflow-shell-safety.md) - Safe shell scripting in workflows
