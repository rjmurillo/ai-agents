# PowerShell Cross-Platform and CI Patterns

## Skill-005: Import-Module Relative Path Prefix (98%)

**Statement**: Always prefix relative file paths with `./` in PowerShell Import-Module commands.

**Problem**:

```powershell
# WRONG - PowerShell treats as module name, searches PSModulePath
Import-Module .github/scripts/AIReviewCommon.psm1
```

**Solution**:

```powershell
# CORRECT - Explicit relative path
Import-Module ./.github/scripts/AIReviewCommon.psm1

# ALTERNATIVE - Absolute path
Import-Module /full/path/to/MyModule.psm1
```

Without `./`, argument is treated as module name and searched only in `$env:PSModulePath`. CI environments have minimal PSModulePath.

**Evidence**: PR #212 → #222

## Skill-006: Cross-Platform Temp Path (95%)

**Statement**: Use `[System.IO.Path]::GetTempPath()` instead of `$env:TEMP` for cross-platform temporary directory access.

**Problem**:

```powershell
# WRONG - Windows-only, returns $null on Linux/macOS
$tempDir = Join-Path $env:TEMP "my-tests"
# ArgumentNullException on Linux
```

**Solution**:

```powershell
# CORRECT - Works on all platforms
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "my-tests"
```

`$env:TEMP` doesn't exist on Linux/macOS. ARM Linux runners fail with ArgumentNullException.

**Evidence**: PR #224, #255

## Skill-008: Exit Code Persistence Prevention (94%)

**Statement**: Add explicit `exit 0` at script end to prevent `$LASTEXITCODE` persistence from external commands.

**Problem**:

```powershell
npm install
npx some-tool --help  # Returns exit code 1 but script continues

Write-Host "All checks passed!"
# Script exits with $LASTEXITCODE = 1 (persisted from npx)
```

**Solution**:

```powershell
npm install
npx some-tool --help

Write-Host "All checks passed!"
exit 0  # Explicitly exit with success
```

`$LASTEXITCODE` persists exit code from last external command. Use explicit `exit 0` or reset with `$global:LASTEXITCODE = 0`.

**Evidence**: PR #298
