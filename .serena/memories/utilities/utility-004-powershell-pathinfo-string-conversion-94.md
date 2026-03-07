# Utility: Powershell Pathinfo String Conversion 94

## Skill-Utility-004: PowerShell PathInfo String Conversion (94%)

**Statement**: Use `(Resolve-Path $Path).Path` or `[string]` cast when string operations needed on resolved path

**Context**: PowerShell scripts using Resolve-Path output for string operations like .Length, -match, or concatenation

**Evidence**: PR #47 - `Resolve-Path` returns PathInfo object, `.Length` returned null without conversion; bug fixed with `.Path` property

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 8/10

**Problem**:

```powershell
# WRONG - PathInfo object doesn't support string operations
$resolvedPath = Resolve-Path ".\relative\path"
$pathLength = $resolvedPath.Length  # Returns NULL - PathInfo has no .Length property
$isMatch = $resolvedPath -match "pattern"  # Type mismatch error
```

**Solution**:

```powershell
# CORRECT - Convert PathInfo to string first
$resolvedPath = (Resolve-Path ".\relative\path").Path  # Extract .Path property
$pathLength = $resolvedPath.Length  # Works - now a string
$isMatch = $resolvedPath -match "pattern"  # Works

# Alternative: Explicit cast
$resolvedPath = [string](Resolve-Path ".\relative\path")
$pathLength = $resolvedPath.Length  # Also works
```

**Detection**: String operation on Resolve-Path result returns null or type error

**Anti-Pattern**: Direct use of Resolve-Path output in string operations without conversion

**Validation**: 1 (PR #47 - cursor[bot] detected bug)

---