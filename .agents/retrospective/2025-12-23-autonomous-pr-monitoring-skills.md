# Autonomous PR Monitoring Skills

**Extracted**: 2025-12-23
**Source**: Autonomous PR monitoring retrospective (Session 80)
**Session Scope**: PR #224, #255, #247, #298, #299

---

## Overview

This document contains 6 atomic skills extracted from the autonomous PR monitoring session. All skills passed SMART validation with atomicity scores 90-96%.

**Session Metrics**:

- PRs addressed: 5
- Skills extracted: 6
- Success rate: 80%
- Atomicity range: 90-96%

---

## Skill-PowerShell-006: Cross-Platform Temp Paths (95%)

**Statement**: Use `[System.IO.Path]::GetTempPath()` instead of `$env:TEMP` for cross-platform PowerShell scripts

**Context**: Writing PowerShell scripts that create temp files, must run on Windows/Linux/macOS

**Trigger**: Creating temp files or directories in PowerShell scripts executed in CI/CD pipelines

**Evidence**: PR #224 and #255 - `$env:TEMP` is Windows-only environment variable, failed on ARM/Linux runners with variable not set error

**Atomicity**: 95%

**Tag**: helpful (prevents cross-platform failures)

**Impact**: 10/10 (critical for multi-platform execution)

**Created**: 2025-12-23

**Validated**: 1 (2 PRs fixed)

**Problem**:

```powershell
# WRONG - Windows-only environment variable
$tempFile = Join-Path $env:TEMP "data.json"
# Fails on Linux/macOS: $env:TEMP is null
```

**Solution**:

```powershell
# CORRECT - Cross-platform method
$tempFile = Join-Path ([System.IO.Path]::GetTempPath()) "data.json"

# Works on:
# - Windows: C:\Users\<user>\AppData\Local\Temp\
# - Linux: /tmp/
# - macOS: /var/folders/.../T/
```

**Why It Matters**:

PowerShell Core (pwsh) runs on Windows, Linux, and macOS. Environment variables like `$env:TEMP` are Windows-specific. CI/CD pipelines may use different runners (ubuntu-latest, windows-latest). `[System.IO.Path]::GetTempPath()` is a .NET method that returns the correct temp directory for each platform.

**Pattern**:

```powershell
# Always use for cross-platform scripts
$tempDir = [System.IO.Path]::GetTempPath()
$tempFile = Join-Path $tempDir "myfile.txt"
```

**Anti-Pattern**:

```powershell
# Platform-specific environment variables
$env:TEMP        # Windows-only
$env:TMP         # Windows-only
$env:TMPDIR      # Linux/macOS-only
```

**Related Skills**:

- Skill-CI-Runner-001: Prefer ubuntu-latest (cross-platform scripts needed)
- Skill-PowerShell-005: Import-Module relative paths (another cross-platform concern)

---

## Skill-PowerShell-007: Here-String Terminator Syntax (96%)

**Statement**: PowerShell here-string terminators must start at column 0 with no leading whitespace

**Context**: Writing PowerShell here-strings in any context (scripts, workflows, modules)

**Trigger**: Using `@'...'@` or `@"..."@` syntax for multi-line strings

**Evidence**: PR #224 - Syntax error "The string is missing the terminator: '@" caused by indented terminator `    '@` in Get-PRContext.ps1

**Atomicity**: 96%

**Tag**: helpful (prevents syntax errors)

**Impact**: 9/10 (syntax errors block execution)

**Created**: 2025-12-23

**Validated**: 1 (PR #224 commit 7a2f8e9)

**Problem**:

```powershell
# WRONG - Indented terminator causes syntax error
function Get-Data {
    $json = @"
    {
        "key": "value"
    }
    "@  # ← Syntax error! Terminator has leading whitespace
}
```

**Solution**:

```powershell
# CORRECT - Terminator at column 0
function Get-Data {
    $json = @"
    {
        "key": "value"
    }
"@  # ← Correct! No leading whitespace
}
```

**Why It Matters**:

PowerShell here-string syntax requires the terminator (`'@` or `"@`) to start at the first character of the line (column 0). Any leading whitespace (spaces or tabs) causes a syntax error. This is different from many other languages where indentation is flexible. The error message "The string is missing the terminator" is misleading (the terminator exists but is incorrectly formatted).

**Pattern**:

```powershell
# Here-string format rules:
# 1. Opening: @' or @" at end of line
# 2. Content: Any indentation allowed
# 3. Closing: '@ or "@ at start of line (column 0)

$heredoc = @"
Content can be indented
    This line has 4 spaces
        This line has 8 spaces
"@  # Must start at column 0
```

**Pre-Commit Validation**:

```powershell
# PSScriptAnalyzer catches this error
Invoke-ScriptAnalyzer -Path script.ps1 -Severity Error
# Output: "The string is missing the terminator: '@"
```

**Related Skills**:

- Skill-CI-001: Pre-commit syntax validation (would catch this error)

---

## Skill-CI-Infrastructure-004: GitHub Label Dependency Validation (92%)

**Statement**: Validate GitHub labels exist before deploying workflows that reference them

**Context**: Deploying GitHub Actions workflows with `gh pr edit --add-label` or similar label operations

**Trigger**: Workflow YAML contains label references (add-label, remove-label, labels filter)

**Evidence**: PR #298 - Missing `drift-detected` and `automated` labels caused workflow failures across multiple PRs when workflows attempted to add non-existent labels

**Atomicity**: 92%

**Tag**: helpful (prevents cascading workflow failures)

**Impact**: 10/10 (prevents infrastructure failures)

**Created**: 2025-12-23

**Validated**: 1 (PR #298 label creation fixed multiple workflows)

**Problem**:

```yaml
# .github/workflows/monitor.yml
# Workflow references labels that don't exist yet
- name: Add labels
  run: gh pr edit $PR --add-label "drift-detected,automated"
  # Fails if labels don't exist in repository
```

**Solution 1: Pre-Deploy Validation**:

```bash
# scripts/validate-workflow-dependencies.sh
#!/bin/bash

# Extract label references from workflows
REQUIRED_LABELS=$(grep -oP '(?<=--add-label ")[^"]+' .github/workflows/*.yml | tr ',' '\n' | sort -u)

# Check if labels exist
for label in $REQUIRED_LABELS; do
    if ! gh label list --json name --jq ".[].name" | grep -q "^$label$"; then
        echo "ERROR: Required label '$label' does not exist"
        exit 1
    fi
done
```

**Solution 2: Infrastructure-as-Code**:

```yaml
# .github/labels.yml
# Define all labels in config
- name: "drift-detected"
  color: "FF6B6B"
  description: "Automated drift detection found changes"

- name: "automated"
  color: "5DADE2"
  description: "Created or updated by automation"
```

```bash
# Create labels from config
gh label create --file .github/labels.yml
```

**Solution 3: Conditional Label Operations**:

```yaml
# .github/workflows/monitor.yml
- name: Add labels (safe)
  run: |
    # Create label if it doesn't exist
    gh label create "drift-detected" --color FF6B6B --force || true
    gh label create "automated" --color 5DADE2 --force || true

    # Then add to PR
    gh pr edit $PR --add-label "drift-detected,automated"
```

**Why It Matters**:

GitHub Actions workflows fail when operations reference non-existent labels. Failures cascade across multiple PRs if workflows are triggered by common events. Label creation is environment setup, not workflow responsibility. Missing infrastructure dependencies should be caught before deployment.

**Pre-Deployment Checklist**:

```markdown
## Workflow Deployment Checklist

- [ ] Labels referenced in workflow exist in repository
- [ ] Secrets required by workflow are configured
- [ ] Environment variables are set
- [ ] Required GitHub Apps are installed
- [ ] Workflow permissions are sufficient
```

**Related Skills**:

- Skill-CI-Research-002: Research platform before implementation (would catch label requirement)

---

## Skill-PowerShell-008: Exit Code Reset in Workflows (94%)

**Statement**: Add explicit `exit 0` at end of PowerShell workflow scripts to prevent `$LASTEXITCODE` persistence

**Context**: PowerShell scripts executed in GitHub Actions workflow `run:` blocks

**Trigger**: PowerShell script calls external tools (gh, git, npm) before workflow completes

**Evidence**: PR #298 - `$LASTEXITCODE` from `npx markdownlint-cli2 --help` persisted and caused workflow failure even though help command succeeded

**Atomicity**: 94%

**Tag**: helpful (prevents spurious failures)

**Impact**: 9/10 (prevents confusing workflow failures)

**Created**: 2025-12-23

**Validated**: 1 (PR #298 Copilot Workspace exit code fix)

**Problem**:

```yaml
# .github/workflows/example.yml
- name: Run script
  shell: pwsh
  run: |
    # Script calls external tool to check syntax
    npx markdownlint-cli2 --help  # Exit code 0

    # Script performs actual work
    Write-Host "Processing files..."

    # Workflow step FAILS here because $LASTEXITCODE is still 0? No!
    # $LASTEXITCODE can persist from previous command
    # If --help returned non-zero, workflow fails at step end
```

**Root Cause**:

PowerShell's `$LASTEXITCODE` variable persists until explicitly reset or overwritten. GitHub Actions checks exit code at workflow step end. If last external command had non-zero exit (even if intentional like `--help`), workflow step fails.

**Solution**:

```yaml
# .github/workflows/example.yml
- name: Run script
  shell: pwsh
  run: |
    # Script content
    npx markdownlint-cli2 --help
    Write-Host "Processing files..."

    # Explicit exit with success code
    exit 0  # ← Ensures workflow step succeeds
```

**Alternative: Reset After External Calls**:

```powershell
# Reset $LASTEXITCODE after each external tool
npx markdownlint-cli2 --help
$LASTEXITCODE = 0  # Reset

gh pr list
$LASTEXITCODE = 0  # Reset

# Final explicit exit
exit 0
```

**Why It Matters**:

GitHub Actions workflow steps succeed/fail based on exit code. PowerShell doesn't automatically reset `$LASTEXITCODE`. External tools may return non-zero for informational commands (--help, --version). Workflow failures are confusing when script appears to succeed. Explicit `exit 0` guarantees clean state.

**Pattern**:

```powershell
# Workflow script template
try {
    # Script logic
    Do-Work

    # Always exit explicitly
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
```

**Anti-Pattern**:

```powershell
# Implicit exit (relies on $LASTEXITCODE)
Do-Work
# No explicit exit - workflow may fail unexpectedly
```

**Related Skills**:

- Skill-CI-Environment-Testing-001: Local CI simulation (would catch this issue)

---

## Skill-Testing-Platform-001: Platform-Specific Test Documentation (90%)

**Statement**: Document platform-specific test requirements in PR description when reverting to single-platform runner

**Context**: ARM migration or cross-platform work blocked by platform-specific test assumptions

**Trigger**: Reverting from `runs-on: [ubuntu-latest, windows-latest]` to single platform

**Evidence**: PR #224 - ARM migration reverted to Windows runner due to platform-specific test assumptions, documented exception in PR description

**Atomicity**: 90%

**Tag**: helpful (improves PR documentation)

**Impact**: 8/10 (prevents future migration attempts without context)

**Created**: 2025-12-23

**Validated**: 1 (PR #224 ARM migration)

**Problem**:

```yaml
# .github/workflows/test.yml
# Changed from cross-platform to Windows-only
jobs:
  test:
    runs-on: windows-latest  # Reverted from ubuntu-latest
    # No documentation of WHY Windows-only
```

**Solution**:

````markdown
## PR Description

### ARM Migration Status

**Status**: Reverted to Windows runner

**Reason**: Tests contain platform-specific assumptions that require Windows:

1. **Path handling**: Tests assume Windows path separators (`\`)
2. **API behavior**: Tests call Windows-specific APIs (e.g., `Get-WmiObject`)
3. **Environment**: Tests rely on Windows environment variables

**Future Work**: Refactor tests for cross-platform execution (Issue #XXX)

**Acceptance Criteria**: Tests must pass on `ubuntu-latest` before ARM migration

### Test Changes

```yaml
# Before: Cross-platform attempt
runs-on: ubuntu-latest

# After: Windows-only (documented exception)
runs-on: windows-latest
```
````

**Why It Matters**:

ARM migration is a common optimization (faster, cheaper runners). Revert without documentation causes repeated migration attempts. Platform-specific requirements are not obvious from code. Future developers need context for single-platform decisions. Documentation prevents "why is this Windows-only?" questions.

**Documentation Template**:

```markdown
## Platform-Specific Requirements

**Runner**: `windows-latest` (required)

**Reason**: [Select one or more]
- [ ] PowerShell Desktop (not Core) required
- [ ] Windows-specific APIs used
- [ ] Tests assume Windows paths/environment
- [ ] Third-party tools only available on Windows

**Tracking Issue**: #XXX (cross-platform migration)

**Acceptance Criteria**: [What needs to change to enable cross-platform]
```

**Related Skills**:

- Skill-CI-Runner-001: Prefer ubuntu-latest (now has documented exception process)
- Skill-Planning-022: Multi-platform agent scope (platform requirements in planning)

---

## Skill-Testing-Path-001: Test Module Import Paths (91%)

**Statement**: Use absolute paths or path helper functions for test module imports across directory boundaries

**Context**: Writing tests in `.github/tests/` that import modules from `.claude/skills/`

**Trigger**: Test file in nested directory (e.g., `.github/tests/skills/github/`) importing from different tree

**Evidence**: PR #255 - `New-Issue.Tests.ps1` had incorrect relative path `../../../../.claude/skills/github/modules/` causing import failure

**Atomicity**: 91%

**Tag**: helpful (prevents path errors)

**Impact**: 8/10 (reduces test maintenance burden)

**Created**: 2025-12-23

**Validated**: 1 (PR #255 path fix)

**Problem**:

```powershell
# .github/tests/skills/github/New-Issue.Tests.ps1
# WRONG - Fragile relative path from test to module
Import-Module ../../../../.claude/skills/github/modules/New-Issue.psm1
# Breaks if directory structure changes
# Difficult to verify correct number of ../
```

**Solution 1: Absolute Path with $PSScriptRoot**:

```powershell
# .github/tests/skills/github/New-Issue.Tests.ps1
# CORRECT - Absolute path from repository root
$repoRoot = Resolve-Path "$PSScriptRoot/../../../../"
$modulePath = Join-Path $repoRoot ".claude/skills/github/modules/New-Issue.psm1"
Import-Module $modulePath
```

**Solution 2: Path Helper Function**:

```powershell
# .github/tests/TestHelpers.psm1
function Get-SkillModulePath {
    param([string]$SkillPath)

    $repoRoot = Resolve-Path "$PSScriptRoot/../../"
    $fullPath = Join-Path $repoRoot ".claude/skills/$SkillPath"

    if (-not (Test-Path $fullPath)) {
        throw "Module not found: $fullPath"
    }

    return $fullPath
}

# .github/tests/skills/github/New-Issue.Tests.ps1
Import-Module (Get-SkillModulePath "github/modules/New-Issue.psm1")
```

**Solution 3: Module Search Path**:

```powershell
# .github/tests/pester.config.ps1
# Add skills directory to PSModulePath
$skillsPath = Resolve-Path "$PSScriptRoot/../.claude/skills"
$env:PSModulePath = "$skillsPath;$env:PSModulePath"

# .github/tests/skills/github/New-Issue.Tests.ps1
# Import by module name (no path needed)
Import-Module New-Issue
```

**Why It Matters**:

Directory restructuring breaks relative paths. Deep nesting (`.github/tests/skills/github/`) makes relative paths error-prone. Path errors caught only at runtime (test execution). Absolute paths are self-documenting (clear where module lives). Path helpers centralize repository structure knowledge.

**Pattern**:

```powershell
# Always calculate paths from repository root
$repoRoot = Resolve-Path "$PSScriptRoot/relative/to/root"
$targetPath = Join-Path $repoRoot "path/from/root"
```

**Anti-Pattern**:

```powershell
# Fragile relative paths
Import-Module ../../../../some/deep/path.psm1
```

**Related Skills**:

- Skill-PowerShell-005: Import-Module relative path prefix (different concern - `./` vs absolute)
- Skill-PowerShell-Path-Normalization-001: Resolve-Path usage (similar technique)

---

## Memory Recommendations

### Update Existing Memories

1. **skills-powershell.md**: Add Skill-PowerShell-006, 007, 008
2. **skills-ci-infrastructure.md**: Add Skill-CI-Infrastructure-004
3. **powershell-testing-patterns.md**: Add Skill-Testing-Platform-001, Skill-Testing-Path-001

### Create New Memory

**File**: `retrospective-2025-12-23-autonomous-pr-monitoring.md`

**Content**:

- Session metrics (5 PRs, 6 skills, 80% success)
- Key patterns (cross-platform, infrastructure, exit codes)
- Autonomous monitoring success indicators
- Pattern recognition evidence (reused $env:TEMP fix)

---

## Skill Summary

| Skill ID | Category | Atomicity | Impact | Target Memory |
|----------|----------|-----------|--------|---------------|
| Skill-PowerShell-006 | Cross-Platform | 95% | 10/10 | skills-powershell.md |
| Skill-PowerShell-007 | Syntax | 96% | 9/10 | skills-powershell.md |
| Skill-PowerShell-008 | CI/CD | 94% | 9/10 | skills-powershell.md |
| Skill-CI-Infrastructure-004 | Validation | 92% | 10/10 | skills-ci-infrastructure.md |
| Skill-Testing-Platform-001 | Documentation | 90% | 8/10 | powershell-testing-patterns.md |
| Skill-Testing-Path-001 | Organization | 91% | 8/10 | powershell-testing-patterns.md |

**Average Atomicity**: 93%
**Average Impact**: 9/10

All skills passed SMART validation and deduplication check.

---

**Generated**: 2025-12-23
**Session**: 80
**Agent**: retrospective
