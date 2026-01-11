# AI Agents Style Guide

> **Principle**: Load context just-in-time. This file is a routing index AND a blocking reference for security patterns.
>
> **Status**: Canonical Source for Security Patterns

## Canonical Sources

| Topic | Source |
|-------|--------|
| PowerShell standards | `scripts/CLAUDE.md`, `AGENTS.md` Coding Standards section |
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

---

## PowerShell Standards

### Function Naming

| Element | Convention | Example |
|---------|------------|---------|
| Functions | `Verb-Noun` (approved verbs only) | `Get-PRContext`, `Test-FilePath` |
| Parameters | `$PascalCase` | `$PullRequest`, `$IncludeChanges` |
| Local variables | `$camelCase` | `$result`, `$lineCount` |
| Script files | `Verb-Noun.ps1` | `Invoke-PRMaintenance.ps1` |

**Approved Verbs**: Use `Get-Verb` to see approved verbs. Common: `Get`, `Set`, `New`, `Remove`, `Test`, `Invoke`, `Update`, `Write`, `Read`.

### Parameter Declaration

```powershell
[CmdletBinding()]
param(
    # Mandatory parameters first
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$RequiredParam,

    # Optional parameters with defaults
    [ValidateRange(1, 100)]
    [int]$Count = 10,

    # Switch parameters last
    [switch]$Force
)
```

### Error Handling

```powershell
$ErrorActionPreference = 'Stop'  # Fail fast

try {
    $result = Invoke-RiskyOperation
    exit 0  # Success
} catch [System.Net.WebException] {
    Write-Error "Network error: $_"
    exit 3  # External error (ADR-035)
} catch {
    Write-Error "Unexpected error: $_"
    exit 1  # General error (ADR-035)
}
```

### Script Documentation

Every script MUST include:

```powershell
<#
.SYNOPSIS
    One-line description.

.DESCRIPTION
    Detailed explanation of what the script does.

.PARAMETER ParamName
    Description of each parameter.

.EXAMPLE
    Invoke-Script -Param "value"
    Description of what this example does.

.NOTES
    EXIT CODES:
    0  - Success: Operation completed
    1  - Error: Validation/logic failure
    2  - Error: Missing required parameter
    3  - Error: GitHub API error
    4  - Error: Authentication failure

    See ADR-035 for complete reference.
#>
```

---

## Exit Code Reference (ADR-035)

| Code | Category | Semantic Meaning |
|------|----------|------------------|
| 0 | Success | Operation completed successfully |
| 1 | Logic Error | Validation failed, assertion violated |
| 2 | Config Error | Missing param, invalid argument, not in git repo |
| 3 | External Error | GitHub API failure, network timeout |
| 4 | Auth Error | Token expired, permission denied, rate limited |
| 5-99 | Reserved | Do not use until standardized |
| 100+ | Script-Specific | Document in script header |

---

## Testing Standards

### Coverage Requirements

| Code Type | Required Coverage | Rationale |
|-----------|-------------------|-----------|
| Security-critical | 100% | No untested security paths |
| Business logic | 80% | Balance coverage with velocity |
| Documentation/Read-only | 60% | Lower risk code |

### Pester Test Pattern

```powershell
Describe 'Function-Name' {
    BeforeAll {
        $script:scriptPath = Join-Path $PSScriptRoot '../script.ps1'
    }

    Context 'Success Scenarios' {
        It 'Should return expected result' {
            $result = & $scriptPath -ValidParam 'value'
            $result | Should -Not -BeNullOrEmpty
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Error Handling' {
        It 'Should exit 2 on missing required parameter' {
            & $scriptPath 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 2
        }

        It 'Should exit 3 on external API error' {
            Mock gh { throw "API error" }
            & $scriptPath -ValidParam 'value' 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 3
        }
    }
}
```

---

## Git Commit Standards

### Format

```text
<type>(<scope>): <description>

<optional body explaining why>

<optional footer with references>
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `style`, `perf`, `ci`, `build`

### AI Attribution (REQUIRED for AI-generated commits)

```text
feat(memory): add semantic search capability

Implements vector-based search with configurable threshold.

Co-Authored-By: Orchestrator agent in Claude Opus 4.5 <noreply@anthropic.com>
```

| Tool | Email | Status |
|------|-------|--------|
| Claude (Anthropic) | `noreply@anthropic.com` | Verified |
| GitHub Copilot | `copilot@github.com` | Verified |
| Cursor | `cursor@cursor.sh` | Verified |
| Factory Droid | See tool documentation | UNVERIFIED |
| Latta | See tool documentation | UNVERIFIED |

### Atomic Commits

- One logical change per commit
- Maximum 5 files OR single topic
- Tests with implementation (same or following commit)

---

## GitHub Actions Standards (ADR-006)

### SHA-Pinned Actions (MANDATORY)

```yaml
# CORRECT - SHA with version comment for security
uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

# WRONG - version tag (supply chain attack vector)
uses: actions/checkout@v4
```

### Expression Interpolation Security

```yaml
# WRONG - vulnerable to command injection
- run: echo "${{ github.event.issue.title }}"

# CORRECT - use environment variables
- run: echo "$ISSUE_TITLE"
  env:
    ISSUE_TITLE: ${{ github.event.issue.title }}
```

### Multi-Line Outputs

```yaml
- name: Generate report
  id: report
  run: |
    {
      echo "content<<EOF"
      echo "Line 1"
      echo "Line 2"
      echo "EOF"
    } >> $GITHUB_OUTPUT
```

### Workflow Architecture

- **Workflows (YAML)**: Orchestration only, calls to scripts
- **Modules (.psm1)**: All business logic
- **Tests (.Tests.ps1)**: Pester tests for modules
- **Maximum size**: 100 lines per workflow
- **Coverage**: 80%+ for exported module functions

---

## Branch Naming

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feat/` | New feature | `feat/oauth-pkce` |
| `fix/` | Bug fix | `fix/null-reference` |
| `docs/` | Documentation | `docs/api-guide` |
| `refactor/` | Restructuring | `refactor/memory-layer` |
| `test/` | Test additions | `test/integration-suite` |
| `chore/` | Maintenance | `chore/deps-update` |
| `ci/` | CI/CD changes | `ci/parallel-jobs` |
| `perf/` | Performance | `perf/query-cache` |

---

## Markdown Standards

### Required Rules (markdownlint)

| Rule | Description |
|------|-------------|
| MD040 | Fenced code blocks MUST have language identifier |
| MD031 | Blank lines required around fenced code blocks |
| MD032 | Blank lines required around lists |
| MD022 | Blank lines required around headings |
| MD033 | Inline HTML restricted; use backticks for generic types |

### Code Block Languages

| Content | Identifier |
|---------|------------|
| C# | `csharp` |
| PowerShell | `powershell` |
| Bash/Shell | `bash` |
| JSON | `json` |
| YAML | `yaml` |
| Markdown | `markdown` |
| Plain text | `text` |
| Python | `python` |

### Generic Type Escaping

```markdown
<!-- CORRECT - escaped with backticks -->
Use `Dictionary<TKey, TValue>` for mappings.

<!-- WRONG - renders incorrectly -->
Use Dictionary<TKey, TValue> for mappings.
```

---

## PR Requirements

All PRs MUST use `.github/PULL_REQUEST_TEMPLATE.md` with:

| Section | Required For | Purpose |
|---------|--------------|---------|
| Summary | All PRs | Brief description |
| Specification References | Feature PRs | Traceability to specs |
| Changes | All PRs | Bulleted list |
| Type of Change | All PRs | Category checkbox |
| Testing | All PRs | Testing approach |
| Agent Review | Security/Architecture | Validation gates |
| Checklist | All PRs | Quality verification |

**Title Format**: Conventional commit style (e.g., `feat(auth): add PKCE flow`)

---

## Code Review Priorities

Review in this order:

1. **Security**: Injection, traversal, secrets, authentication
2. **Correctness**: Logic errors, edge cases, null handling
3. **Exit Codes**: ADR-035 compliance
4. **Test Coverage**: Meets required thresholds
5. **Style**: Naming, documentation, formatting

---

## Agent Protocol Patterns

### RFC 2119 Keywords

| Keyword | Meaning |
|---------|---------|
| **MUST** / **REQUIRED** | Absolute requirement; violation is protocol failure |
| **MUST NOT** | Absolute prohibition |
| **SHOULD** / **RECOMMENDED** | Strong recommendation; deviation requires justification |
| **SHOULD NOT** | Strong discouragement |
| **MAY** / **OPTIONAL** | Truly optional |

### Handoff Documents

- **HANDOFF.md**: Read-only reference (MUST NOT modify)
- **Session logs**: Write session context to `.agents/sessions/`
- **Serena memory**: Cross-session context via memory tools

### Memory System (Multi-Tier)

| Tier | Tool | Purpose |
|------|------|---------|
| Serena (preferred) | `mcp__serena__read_memory` | Project-specific, file-based |
| Forgetful | `memory-search_nodes` | Semantic search, knowledge graph |
| VS Code memory (last resort) | `memory/view` | Platform-specific, not shared |

---

## ADR Format

ADRs follow MADR 4.0 format in `.agents/architecture/ADR-NNN-kebab-case-title.md`:

| Section | Purpose |
|---------|---------|
| Status | Proposed, Accepted, Deprecated, Superseded |
| Date | Decision date |
| Context | Problem description |
| Decision | Clear statement of choice |
| Rationale | Why this option, alternatives considered |
| Consequences | Positive, Negative, Neutral impacts |

---

## Cross-Reference Standards

### Within `.agents/` Directory

```markdown
See [ADR-035](architecture/ADR-035-exit-code-standardization.md)
```

### From Other Directories

```markdown
See [PROJECT-CONSTRAINTS.md](.agents/governance/PROJECT-CONSTRAINTS.md)
```

### Memory References (Instructive)

```markdown
Read the `usage-mandatory` memory using `mcp__serena__read_memory` with `memory_file_name="usage-mandatory"`
- If Serena MCP is unavailable, read `.serena/memories/usage-mandatory.md`
```

---

## Quick Reference

### Do Use

- Active voice, short sentences
- Text status indicators: `[PASS]`, `[FAIL]`, `[WARNING]`
- Data instead of adjectives
- Mermaid diagrams for complexity
- Clear verdicts and conclusions

### Avoid

- Em dashes, emojis
- Sycophantic phrases, hedging language
- Marketing buzzwords
- Passive voice
- Long paragraphs (5+ sentences)
