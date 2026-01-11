# AI Agents Style Guide

> **Principle**: Load context just-in-time. This file is a routing index and blocking reference for security patterns.

**Status**: Canonical Source for Security Patterns

## Canonical Sources

| Topic | Source |
|-------|--------|
| PowerShell standards | `scripts/AGENTS.md`, `AGENTS.md` Coding Standards section |
| Exit codes | `ADR-035` in `.agents/architecture/` |
| Output schemas | `ADR-028` in `.agents/architecture/` |
| Workflow architecture | `ADR-006` in `.agents/architecture/` |
| Skill usage | `.serena/memories/usage-mandatory.md` |
| Session protocol | `.agents/SESSION-PROTOCOL.md` |
| Project constraints | `.agents/governance/PROJECT-CONSTRAINTS.md` |
| Communication style | `src/STYLE-GUIDE.md` |
| Naming conventions | `.agents/governance/naming-conventions.md` |
| PR template | `.github/PULL_REQUEST_TEMPLATE.md` |

---

## Security Patterns (BLOCKING)

These patterns cause immediate rejection. All agents MUST memorize and apply them.

### Path Traversal Prevention (CWE-22)

```powershell
# WRONG - vulnerable to path traversal attacks
$Path.StartsWith($Base)

# CORRECT - resolves symlinks and normalizes paths
$resolvedPath = [IO.Path]::GetFullPath($Path)
$resolvedBase = [IO.Path]::GetFullPath($Base) + [IO.Path]::DirectorySeparatorChar
$resolvedPath.StartsWith($resolvedBase, [StringComparison]::OrdinalIgnoreCase)
```

**Attack Vector**: `../../../etc/passwd` bypasses naive prefix checks.

### Command Injection Prevention (CWE-78)

```powershell
# WRONG - unquoted arguments allow injection
npx tsx $Script $Arg

# CORRECT - always quote arguments containing user input
npx tsx "$Script" "$Arg"
```

**Attack Vector**: `; rm -rf /` in unquoted arguments executes arbitrary commands.

### Variable Interpolation Security

```powershell
# WRONG - colon is PowerShell scope operator, breaks interpolation
"Processing line $Num:"
"Value: $Config:"

# CORRECT - use subexpression operator for safe interpolation
"Processing line $($Num):"
"Value: $($Config):"
```

**Why**: PowerShell interprets `$Num:` as accessing the `Num:` drive, not the variable `$Num`.

### Secure String Handling

```powershell
# WRONG - exposes secrets in logs
Write-Host "Using token: $($env:GITHUB_TOKEN)"
Write-Verbose "Password is: $password"

# CORRECT - never log sensitive values
Write-Host "Using token: [REDACTED]"
Write-Verbose "Password provided: $($null -ne $password)"

# CORRECT - use SecureString for sensitive parameters
param(
    [SecureString]$Password
)

# CORRECT - clear secrets when done
try {
    # Use secret
} finally {
    Remove-Variable -Name 'SecretValue' -ErrorAction SilentlyContinue
}
```

### File Path Security

```powershell
# WRONG - accepts any path
param([string]$FilePath)
Get-Content $FilePath

# CORRECT - validate path is within allowed directory
param([string]$FilePath)
$allowed = [IO.Path]::GetFullPath($PSScriptRoot)
$resolved = [IO.Path]::GetFullPath($FilePath)
if (-not $resolved.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar)) {
    throw "Path traversal attempt detected"
}
Get-Content $resolved
```

### Expression Interpolation Security (GitHub Actions)

```yaml
# WRONG - vulnerable to command injection
- run: echo "${{ github.event.issue.title }}"

# CORRECT - use environment variables
- run: echo "$ISSUE_TITLE"
  env:
    ISSUE_TITLE: ${{ github.event.issue.title }}
```

### SHA-Pinned Actions (MANDATORY)

```yaml
# CORRECT - SHA with version comment for security
uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

# WRONG - version tag (supply chain attack vector)
uses: actions/checkout@v4
```

---

## Quick Reference

### Testing Coverage Requirements

| Code Type | Required Coverage |
|-----------|-------------------|
| Security-critical | 100% |
| Business logic | 80% |
| Documentation/Read-only | 60% |

### AI Attribution (REQUIRED for AI-generated commits)

| Tool | Email | Status |
|------|-------|--------|
| Claude (Anthropic) | `noreply@anthropic.com` | Verified |
| GitHub Copilot | `copilot@github.com` | Verified |
| Cursor | `cursor@cursor.sh` | Verified |
| Factory Droid | See tool documentation | UNVERIFIED |
| Latta | See tool documentation | UNVERIFIED |

### Code Review Priorities

Review in this order:

1. **Security**: Injection, traversal, secrets, authentication
2. **Correctness**: Logic errors, edge cases, null handling
3. **Exit Codes**: ADR-035 compliance
4. **Test Coverage**: Meets required thresholds
5. **Style**: Naming, documentation, formatting

### RFC 2119 Keywords

| Keyword | Meaning |
|---------|---------|
| **MUST** / **REQUIRED** | Absolute requirement; violation is protocol failure |
| **MUST NOT** | Absolute prohibition |
| **SHOULD** / **RECOMMENDED** | Strong recommendation; deviation requires justification |
| **SHOULD NOT** | Strong discouragement |
| **MAY** / **OPTIONAL** | Truly optional |

---

## For Complete Details

Load detailed documentation just-in-time from these sources:

- **PowerShell coding standards**: `scripts/AGENTS.md`
- **Exit code semantics**: `.agents/architecture/ADR-035-exit-code-standardization.md`
- **Workflow patterns**: `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`
- **Full agent instructions**: `AGENTS.md`
- **Communication style**: `src/STYLE-GUIDE.md`
