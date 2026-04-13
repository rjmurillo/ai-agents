# Powershell: Importmodule Relative Path Prefix 98

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

## Related

- [powershell-001-casesensitive-regex-matching](powershell-001-casesensitive-regex-matching.md)
- [powershell-001-variable-interpolation-safety](powershell-001-variable-interpolation-safety.md)
- [powershell-002-nullsafety-for-contains-operator](powershell-002-nullsafety-for-contains-operator.md)
- [powershell-002-pester-hashtable-initialization](powershell-002-pester-hashtable-initialization.md)
- [powershell-003-array-coercion-for-single-items](powershell-003-array-coercion-for-single-items.md)
