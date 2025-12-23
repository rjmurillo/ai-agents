# PowerShell Skills

**Extracted**: 2025-12-20
**Source**: PR #79 retrospective analysis

## Skill-PowerShell-001: Variable Interpolation Safety

**Statement**: Use subexpression syntax `$($var)` or braced syntax `${var}` when variable is followed by colon in double-quoted strings to prevent scope qualifier ambiguity.

**Context**: PowerShell string interpolation

**Evidence**: PR #79 - Get-PRContext.ps1 line 64 syntax error from `$PullRequest:` pattern, fixed by changing to `$($PullRequest):`

**Atomicity**: 95%

**Problem**:

```powershell
# WRONG - Colon after variable causes scope qualifier ambiguity
$message = "Pull Request: $PullRequest: Title"  # Syntax error!
```

**Solution**:

```powershell
# CORRECT - Use subexpression syntax
$message = "Pull Request: $($PullRequest): Title"

# ALTERNATIVE - Use braced syntax
$message = "Pull Request: ${PullRequest}: Title"
```

**Why It Matters**:

PowerShell interprets `$var:` as a scope qualifier (like `$global:var` or `$script:var`). When a colon immediately follows a variable name in string interpolation, it must be wrapped in subexpression `$()` or braces `${}` to disambiguate.

**Validation**: 1 (PR #79)

---

## Skill-PowerShell-002: Null-Safety for Contains Operator

**Statement**: Use `@($raw) | Where-Object { $_ }` before `-contains` to filter nulls from potentially empty arrays

**Context**: When using `-contains` operator on potentially empty PowerShell arrays

**Evidence**: PR #212 cursor[bot] #2628872634 - null method call on `@($null)` array

**Atomicity**: 94%

**Tag**: helpful (prevents null reference errors)

**Impact**: 10/10 (prevents runtime failures)

**Created**: 2025-12-20

**Problem**:

```powershell
# WRONG - Creates array with null if results are empty
$results = @(Get-Something)
if ($results -contains $item) { }  # Fails with null method call if results empty

# WRONG - No null protection
$results = Get-Something
if ($results -contains $item) { }  # Fails on empty results
```

**Solution**:

```powershell
# CORRECT - Filters nulls before contains
$results = @(Get-Something) | Where-Object { $_ }
if ($results -contains $item) { }
```

**Why It Matters**:

PowerShell's `@()` operator coerces values to arrays but `@($null)` creates a single-element array containing null, not an empty array. When you call `-contains` on this array, it may invoke methods on null elements, causing runtime errors.

**Pattern**:

```powershell
# Safe pattern for potentially empty results
$safeResults = @($rawResults) | Where-Object { $_ }
```

**Anti-Pattern**:

```powershell
# Unsafe - can create @($null)
$unsafeResults = @($rawResults)
```

**Validation**: 1 (PR #212)

---

## Skill-PowerShell-003: Array Coercion for Single Items

**Statement**: Wrap single strings with `@()` before `-contains` operator to prevent type errors

**Context**: When variable may be single string or array, before using `-contains`

**Evidence**: PR #212 cursor[bot] #2628872629 - `-contains` failed on single string

**Atomicity**: 95%

**Tag**: helpful (prevents type errors)

**Impact**: 9/10 (enables consistent array operations)

**Created**: 2025-12-20

**Problem**:

```powershell
# WRONG - Fails if $Milestone is a single string
if ($Milestone -contains $label) { }  # Type error!
```

**Solution**:

```powershell
# CORRECT - Coerces single string to array
if (@($Milestone) -contains $label) { }
```

**Why It Matters**:

PowerShell's `-contains` operator works on arrays. If the left operand is a single string, PowerShell treats it as a character array, not a string collection. Wrapping with `@()` ensures consistent array behavior.

**Pattern**:

```powershell
# Safe pattern for potentially single-item variable
@($variable) -contains $item
```

**Anti-Pattern**:

```powershell
# Unsafe - assumes variable is array
$variable -contains $item
```

**Validation**: 1 (PR #212)

---

## Skill-PowerShell-004: Case-Insensitive String Matching

**Statement**: Call `.ToLowerInvariant()` on strings before `-contains` for case-insensitive matching

**Context**: When matching labels, milestones, or other user input where case should not matter

**Evidence**: PR #212 Copilot review - 3 instances of case-sensitive matching bugs

**Atomicity**: 96%

**Tag**: helpful (prevents case-sensitivity bugs)

**Impact**: 8/10 (improves user experience)

**Created**: 2025-12-20

**Problem**:

```powershell
# WRONG - Case-sensitive by default
if ($labels -contains $input) { }  # Fails if case differs
```

**Solution**:

```powershell
# CORRECT - Normalize case before comparison
if ($labels.ToLowerInvariant() -contains $input.ToLowerInvariant()) { }
```

**Why It Matters**:

PowerShell's `-contains` operator is case-sensitive by default. When matching user input (labels, milestones, tags), case should typically not matter. Normalizing both operands to lowercase ensures consistent matching.

**Pattern**:

```powershell
# Safe pattern for case-insensitive matching
$collection.ToLowerInvariant() -contains $item.ToLowerInvariant()

# Alternative: Use -in operator with lowercase
$item.ToLowerInvariant() -in $collection.ToLowerInvariant()
```

**Anti-Pattern**:

```powershell
# Unsafe - case-sensitive
$collection -contains $item
```

**Note**: `.ToLowerInvariant()` is preferred over `.ToLower()` for culture-independent comparisons.

**Validation**: 1 (PR #212, 3 instances fixed)

---

## Skill-PowerShell-Security-001: Hardened Regex for AI Output (96%)

**Statement**: Use regex `^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _\.-]*[A-Za-z0-9])?$` for AI-generated label/milestone parsing (prevents trailing special chars)

**Context**: When parsing AI-generated structured output (labels, milestones, tags)

**Evidence**: AIReviewCommon.psm1 prevented injection, Session 44 drop-in replacement succeeded. Updated in PR #212 (Copilot review) to fix trailing special char vulnerability.

**Atomicity**: 96%

**Tag**: helpful (security)

**Impact**: 9/10

**Created**: 2025-12-20

**Updated**: 2025-12-20 (PR #212 - fixed trailing special char vulnerability)

**Pattern**:

```powershell
function Get-LabelsFromAIOutput {
    param([string]$Output)

    # Hardened regex blocks shell metacharacters AND trailing special chars
    # Pattern breakdown:
    # ^(?=.{1,50}$)       - Lookahead: total length 1-50 characters
    # [A-Za-z0-9]         - Must start with alphanumeric
    # (?:[A-Za-z0-9 _\.-]*[A-Za-z0-9])?  - Optional: middle chars + alphanumeric end
    # This prevents strings like "bug-" or "A-" by requiring alphanumeric end
    $validPattern = '^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _\.-]*[A-Za-z0-9])?$'

    # Extract labels from JSON
    if ($Output -match '"labels"\s*:\s*\[([^\]]+)\]') {
        $Matches[1] -split ',' | ForEach-Object {
            $_.Trim().Trim('"').Trim("'")
        } | Where-Object {
            $_ -match $validPattern
        }
    }
}
```

**Previous Pattern (VULNERABLE)**:

```powershell
# WRONG - Optional [a-zA-Z0-9]? allows trailing special chars like "bug-"
$validPattern = '^[a-zA-Z0-9][a-zA-Z0-9 _\-\\.]{0,48}[a-zA-Z0-9]?$'
```

**Blocked Metacharacters**: `;`, `|`, `` ` ``, `$`, `(`, `)`, `\n`, `&`, `<`, `>`

**Anti-Pattern**: Using bash `xargs`, `tr`, or unquoted variables for AI output parsing

**Source**: `.agents/retrospective/2025-12-20-pr-211-security-miss.md`

**Validation**: 1 (Session 44 remediation)

---

## Skill-PowerShell-005: Import-Module Relative Path Prefix (98%)

**Statement**: Always prefix relative file paths with `./` in PowerShell Import-Module commands

**Context**: When importing PowerShell modules from file paths in CI/CD workflows or scripts

**Trigger**: Writing `Import-Module` with path to `.psm1` or `.psd1` file

**Evidence**: PR #212 (commit 981ebf7): `Import-Module .github/scripts/AIReviewCommon.psm1` failed in CI. PR #222 fixed by adding `./` prefix → `Import-Module ./.github/scripts/AIReviewCommon.psm1`

**Atomicity**: 98%

**Tag**: helpful (prevents runtime failures)

**Impact**: 9/10

**Created**: 2025-12-21

**Problem**:

```powershell
# WRONG - PowerShell treats as module name, searches PSModulePath
Import-Module .github/scripts/AIReviewCommon.psm1

# WRONG - Same issue with different path
Import-Module scripts/MyModule.psm1
```

**Solution**:

```powershell
# CORRECT - Explicit relative path with ./ prefix
Import-Module ./.github/scripts/AIReviewCommon.psm1

# CORRECT - Absolute path also works
Import-Module /full/path/to/MyModule.psm1

# CORRECT - Module from PSModulePath (no path prefix needed)
Import-Module PSScriptAnalyzer
```

**Why It Matters**:

PowerShell distinguishes "module names" from "file paths". Without `./`, the argument is treated as a module name and searched only in `$env:PSModulePath` directories. CI environments have minimal PSModulePath (modules not installed), so file path imports fail without explicit `./` prefix.

**Cross-platform Note**:

- Works on Windows, Linux, macOS (PowerShell Core 7+)
- `./` is portable across all platforms
- Backslash `.\` works on Windows but not portable

**Validation**: 1 (PR #212 → #222)

---

## Skill-PowerShell-006: Cross-Platform Temp Path (95%)

**Statement**: Use `[System.IO.Path]::GetTempPath()` instead of `$env:TEMP` for cross-platform temporary directory access

**Context**: When creating temporary files or directories in PowerShell scripts that run on Windows, Linux, or macOS

**Trigger**: Writing code that creates temporary files or directories

**Evidence**: PR #224 (Pester test failures on ARM Linux), PR #255 (Generate-Skills.Tests.ps1, Generate-Agents.Tests.ps1)

**Atomicity**: 95%

**Tag**: critical (cross-platform compatibility)

**Impact**: 10/10

**Created**: 2025-12-23

**Problem**:

```powershell
# WRONG - Windows-only, returns $null on Linux/macOS
$tempDir = Join-Path $env:TEMP "my-tests"
# ArgumentNullException: Value cannot be null. (Parameter 'Path')
```

**Solution**:

```powershell
# CORRECT - Works on all platforms
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "my-tests"

# ALTERNATIVE - Function wrapper
function Get-TempDirectory {
    [System.IO.Path]::GetTempPath()
}
$tempDir = Join-Path (Get-TempDirectory) "my-tests"
```

**Why It Matters**:

`$env:TEMP` is a Windows environment variable that doesn't exist on Linux or macOS. When running PowerShell scripts on ARM Linux runners (GitHub Actions), `$env:TEMP` returns `$null`, causing `Join-Path` to fail with ArgumentNullException.

**Validation**: 2 (PR #224, PR #255)

---

## Skill-PowerShell-007: Here-String Terminator Column Zero (96%)

**Statement**: Here-string terminators (`"@` or `'@`) must start at column 0 with no leading whitespace

**Context**: Writing multi-line here-strings in PowerShell scripts

**Trigger**: Using here-string syntax `@"..."@` or `@'...'@`

**Evidence**: PR #224 (Detect-AgentDrift.Tests.ps1 line 591 syntax error)

**Atomicity**: 96%

**Tag**: critical (syntax error)

**Impact**: 9/10

**Created**: 2025-12-23

**Problem**:

```powershell
# WRONG - Terminator has leading whitespace (indented)
$content = @"
Some content here
  "@    # ERROR: The string is missing the terminator: "@
```

**Solution**:

```powershell
# CORRECT - Terminator at column 0
$content = @"
Some content here
"@
# Works even if rest of script is indented
```

**Why It Matters**:

PowerShell here-string syntax is strict: the closing `"@` or `'@` must be the only characters on its line AND must start at column 0 (no leading whitespace). This is a common issue when copy-pasting code or when auto-formatters indent the terminator.

**Detection**: Error message will say "The string is missing the terminator: `"@`" with a line number earlier than the actual terminator.

**Fix Command**:

```bash
# Remove leading whitespace from line 591
sed -i '591s/^[[:space:]]*//' script.ps1
```

**Validation**: 1 (PR #224)

---

## Skill-PowerShell-008: Exit Code Persistence Prevention (94%)

**Statement**: Add explicit `exit 0` at script end to prevent `$LASTEXITCODE` persistence from external commands

**Context**: PowerShell scripts that call external tools (npm, npx, git) whose exit codes persist in `$LASTEXITCODE`

**Trigger**: Script calls external commands in verification/setup steps

**Evidence**: PR #298 (Copilot Workspace Setup failed with exit code 1 despite all checks passing)

**Atomicity**: 94%

**Tag**: helpful (prevents false failures)

**Impact**: 9/10

**Created**: 2025-12-23

**Problem**:

```powershell
# Script that calls external commands
npm install
npx some-tool --help  # Returns exit code 1 but script continues

Write-Host "All checks passed!"
# Script exits with $LASTEXITCODE = 1 (persisted from npx)
```

**Solution**:

```powershell
# CORRECT - Reset exit code explicitly at end
npm install
npx some-tool --help  # Returns exit code 1

Write-Host "All checks passed!"
exit 0  # Explicitly exit with success
```

**Why It Matters**:

`$LASTEXITCODE` persists the exit code of the most recent external command. If a command like `npx markdownlint-cli2 --help` returns non-zero but doesn't cause script termination, the script may exit with that exit code even if all logic completed successfully.

**Alternative Solutions**:

```powershell
# Reset after each external command
npx some-tool --help
$global:LASTEXITCODE = 0

# Check and reset explicitly
if ($LASTEXITCODE -ne 0 -and $ExpectedNonZero) {
    $global:LASTEXITCODE = 0
}
```

**Validation**: 1 (PR #298)

---

## Related Files

- Get-PRContext.ps1 - Original syntax error
- AIReviewCommon.psm1 - Import-Module path fix (PR #212 → #222)
- Source: PR #79 retrospective
- Source: `.agents/sessions/2025-12-21-session-56-ai-triage-retrospective.md`
