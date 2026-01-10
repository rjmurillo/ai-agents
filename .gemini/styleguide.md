# AI Agents Style Guide

> **Principle**: Load context just-in-time. This file is a routing index, not a content dump.

## Canonical Sources

| Topic | Source |
|-------|--------|
| PowerShell standards | `scripts/CLAUDE.md` |
| Exit codes | `ADR-035` in `.agents/architecture/` |
| Output schemas | `ADR-028` in `.agents/architecture/` |
| Workflow architecture | `ADR-006` in `.agents/architecture/` |
| Skill usage | `.serena/memories/usage-mandatory.md` |
| Session protocol | `.agents/SESSION-PROTOCOL.md` |
| Project constraints | `.agents/governance/PROJECT-CONSTRAINTS.md` |

## Security Patterns (Blocking)

These cause immediate rejection. Memorize them.

### Path Traversal (CWE-22)

```powershell
# WRONG
$Path.StartsWith($Base)

# CORRECT
$resolvedPath = [IO.Path]::GetFullPath($Path)
$resolvedBase = [IO.Path]::GetFullPath($Base) + [IO.Path]::DirectorySeparatorChar
$resolvedPath.StartsWith($resolvedBase, [StringComparison]::OrdinalIgnoreCase)
```

### Command Injection (CWE-78)

```powershell
# WRONG
npx tsx $Script $Arg

# CORRECT
npx tsx "$Script" "$Arg"
```

### Variable Interpolation

```powershell
# WRONG - colon is scope operator
"Line $Num:"

# CORRECT
"Line $($Num):"
```

## Testing

| Code Type | Coverage |
|-----------|----------|
| Security-critical | 100% |
| Business logic | 80% |
| Documentation/Read-only | 60% |

## Commits

Format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore` (use scopes such as `ci` as needed, e.g., `chore(ci)` for CI changes)

AI attribution:

| Tool | Email |
|------|-------|
| Claude | `noreply@anthropic.com` |
| Copilot | `copilot@github.com` |
| Cursor | `cursor@cursor.sh` |
| Factory Droid | UNVERIFIED (see tool docs) |
| Latta | UNVERIFIED (see tool docs) |

## GitHub Actions

- SHA-pin all actions
- No `${{ }}` in `run:` blocks - use `env:` instead
- Logic in .psm1 modules, not YAML (ADR-006)

## Code Review Priorities

1. Security (injection, traversal, secrets)
2. Correctness (logic, edge cases)
3. Exit codes (ADR-035 compliance)
4. Test coverage targets met
