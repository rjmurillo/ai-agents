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

## Related Files

- Get-PRContext.ps1 - Original syntax error
- AIReviewCommon.psm1 - Import-Module path fix (PR #212 → #222)
- Source: PR #79 retrospective
- Source: `.agents/sessions/2025-12-21-session-56-ai-triage-retrospective.md`

## Skill-Perf-001: PowerShell -NoProfile for Non-Interactive Scripts

**Statement**: ALWAYS use `pwsh -NoProfile` when invoking PowerShell scripts from Claude Code Bash tool, CI/CD workflows, or any non-interactive automation

**Context**: When Claude Code uses Bash tool to invoke PowerShell scripts, or when spawning PowerShell processes from automation

**Evidence**:
- Benchmark testing: 1,044ms → 183ms per spawn (82.4% faster)
- Profile overhead: 861ms from PSReadLine and prompt customization
- Claude session impact: 10 calls = 10.4s → 1.8s (8.6s saved per session)

**Atomicity**: 98%

**Tag**: critical (Claude Code performance)

**Impact**: 10/10 (affects every session)

**Created**: 2025-12-23

**Pattern**:

```python
# Claude Code using Bash tool - CORRECT
Bash(command="pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 268")

# GitHub Actions workflow - CORRECT
- name: Run script
  run: pwsh -NoProfile ./.github/scripts/MyScript.ps1
```

**Anti-Pattern**:

```python
# WRONG - Claude Code wasting 861ms per call
Bash(command="pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 268")

# WRONG - CI/CD wasting 861ms per spawn
- name: Run script
  run: pwsh ./.github/scripts/MyScript.ps1
```

**Why It Matters**:

User profiles load interactive modules (PSReadLine, prompt customization) that add 861ms overhead per spawn. Non-interactive automation doesn't need these. `-NoProfile` skips profile loading entirely.

**Claude Code Specific Impact**:

Every `Bash(command="pwsh ...")` call in a Claude session spawns a new process. Without `-NoProfile`:
- Single call: 1,044ms (user waits)
- 10 calls: 10.4 seconds wasted
- 20 calls: 20.9 seconds wasted

With `-NoProfile`:
- Single call: 183ms
- 10 calls: 1.8 seconds
- 20 calls: 3.7 seconds

**Validation**: Measured 2025-12-23 (test-noprofile.ps1)

