# PowerShell Coding Standards

> **Scope**: Scripts directory only. Auto-loaded when working in `scripts/`.
> **Primary Reference**: Root CLAUDE.md and AGENTS.md take precedence.

## Language Constraint

**PowerShell only** (.ps1/.psm1) per ADR-005.

No bash or Python scripts in this directory. Cross-platform consistency via PowerShell.

## Script Structure

```powershell
<#
.SYNOPSIS
Brief description

.PARAMETER ParamName
Parameter description

.EXAMPLE
Example usage
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RequiredParam,

    [string]$OptionalParam
)

$ErrorActionPreference = 'Stop'

# Functions
function Verb-Noun {
    [CmdletBinding()]
    param()

    # Implementation
}

# Main logic
try {
    Verb-Noun
    exit 0
} catch {
    Write-Error "An error occurred: $_"
    exit 1
}
```

## Naming Conventions

- Scripts: `Verb-Noun.ps1` (PascalCase, approved verbs)
- Functions: `Verb-Noun` (PascalCase, approved verbs)
- Variables: `$camelCase` or `$PascalCase` for exported
- Parameters: `$PascalCase`

## Error Handling

```powershell
$ErrorActionPreference = 'Stop'  # Fail fast

try {
    # Operations
    exit 0  # Success
} catch {
    Write-Error $_.Exception.Message
    exit 1  # Failure
}
```

## Cross-Platform Patterns

```powershell
# Path separators
$path = Join-Path $dir $file  # Not "$dir/$file"

# Line endings
Get-Content -Raw  # Preserves line endings

# Case sensitivity
Use [StringComparison]::OrdinalIgnoreCase for comparisons
```

## Testing

- Pester tests in `tests/` or adjacent to scripts
- Test isolation: No global state
- Parameterized tests: `@()` arrays
- CI validation: All tests run on push

## Module Structure

```powershell
# {Module}.psm1
function Export-Function1 { }
function Export-Function2 { }

Export-ModuleMember -Function Export-Function1, Export-Function2
```

## Security

- No secrets in scripts (use environment variables or parameters)
- Validate input at system boundaries
- Use approved parameter sets for mutually exclusive options

## Related References

- Code style: `.serena/memories/code-style-conventions.md`
- Skill development: `.claude/skills/CLAUDE.md`
- ADR-005: PowerShell-only architecture
