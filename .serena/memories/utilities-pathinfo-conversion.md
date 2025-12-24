# PowerShell PathInfo String Conversion

**Statement**: Use `(Resolve-Path $Path).Path` or `[string]` cast when string operations needed on resolved path

**Context**: PowerShell scripts using Resolve-Path output for string operations

**Evidence**: PR #47 - Resolve-Path returns PathInfo object, .Length returned null without conversion

**Atomicity**: 94%

**Impact**: 8/10

## Problem

```powershell
# WRONG - PathInfo object doesn't support string operations
$resolvedPath = Resolve-Path ".\relative\path"
$pathLength = $resolvedPath.Length  # Returns NULL
$isMatch = $resolvedPath -match "pattern"  # Type mismatch
```

## Solution

```powershell
# CORRECT - Convert PathInfo to string first
$resolvedPath = (Resolve-Path ".\relative\path").Path
$pathLength = $resolvedPath.Length  # Works

# Alternative: Explicit cast
$resolvedPath = [string](Resolve-Path ".\relative\path")
```

## Detection

String operation on Resolve-Path result returns null or type error.
