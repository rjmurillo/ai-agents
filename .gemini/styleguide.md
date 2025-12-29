# AI Agents Repository Style Guide

This style guide defines the coding standards, conventions, and best practices for the ai-agents repository. Gemini Code Assist should use these guidelines when reviewing code and providing suggestions.

## Project Overview

This is a multi-agent system for software development that supports VS Code (GitHub Copilot), GitHub Copilot CLI, and Claude Code CLI. The repository contains:

- PowerShell installation and utility scripts
- Markdown agent definitions and documentation
- GitHub Actions workflows
- Bash utility scripts for CI/CD

## PowerShell Standards

### Function Naming

Use PascalCase with approved PowerShell verbs. Function names should follow the Verb-Noun pattern.

**Approved verbs** (common subset):

- `Get`, `Set`, `New`, `Remove` - CRUD operations
- `Install`, `Uninstall` - Deployment operations
- `Test`, `Invoke` - Execution operations
- `Initialize`, `Resolve` - Setup operations
- `Copy`, `Move`, `Write`, `Read` - I/O operations
- `Import`, `Export` - Data transfer operations

**Good examples**:

```powershell
function Get-InstallConfig { }
function Install-AgentFiles { }
function Test-GitRepository { }
function Initialize-Destination { }
function Resolve-DestinationPath { }
```

**Avoid**:

```powershell
function getConfig { }          # Wrong: camelCase
function DoInstall { }          # Wrong: non-approved verb
function CheckGitRepository { } # Wrong: use Test-
```

### Parameter Declaration

Use `[CmdletBinding()]` for all functions. Declare parameters with type annotations and validation attributes.

**Good example**:

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$SourcePath,

    [Parameter()]
    [ValidateSet("Claude", "Copilot", "VSCode")]
    [string]$Environment,

    [switch]$Force,

    [switch]$WhatIf
)
```

### Error Handling

Use try/catch blocks for error handling. Use `Write-Error` for errors, `Write-Warning` for warnings, and `Write-Verbose` for debug information.

**Good example**:

```powershell
try {
    $result = Get-Content -Path $FilePath -ErrorAction Stop
    Write-Verbose "Successfully read file: $FilePath"
    return $result
}
catch {
    Write-Error "Failed to read file '$FilePath': $_"
    throw
}
```

**Avoid**:

```powershell
# Wrong: Using Write-Host for debugging
Write-Host "Reading file..."

# Wrong: Not handling errors
$result = Get-Content -Path $FilePath
```

### Script Documentation

Include comment-based help with `.SYNOPSIS`, `.DESCRIPTION`, `.PARAMETER`, and `.EXAMPLE` sections.

**Good example**:

```powershell
<#
.SYNOPSIS
    Installs agent files to the specified destination.

.DESCRIPTION
    Copies agent definition files from the source directory to the target
    installation path. Supports both global and repository-level installations.

.PARAMETER SourcePath
    The path to the source agent files.

.PARAMETER Force
    Overwrite existing files without prompting.

.EXAMPLE
    Install-AgentFiles -SourcePath ".\src\claude" -DestPath "$HOME\.claude\agents"
#>
```

### Common Patterns

Use `$ErrorActionPreference = "Stop"` at script start for consistent error handling.

Support `-WhatIf` and `-Verbose` parameters for scripts that modify state.

Use `Join-Path` instead of string concatenation for paths.

**Good example**:

```powershell
$DestFile = Join-Path $DestDir $File.Name
```

**Avoid**:

```powershell
$DestFile = "$DestDir\$($File.Name)"  # Wrong: platform-specific separator
```

## Markdown Standards

**Prettier Compatibility Policy**: This repository aligns with [Prettier markdown formatting](https://github.com/DavidAnson/markdownlint/blob/main/doc/Prettier.md) to enable seamless copying of markdown files between projects using PackedPrettier. As a result, certain style rules are delegated to Prettier for automatic formatting rather than being enforced by markdownlint.

### Heading Style

**Policy**: Prettier handles heading style formatting. ATX-style headings (`#`) are preferred but not enforced by linting.

**Preferred** (ATX-style):

```markdown
# Top-Level Heading

## Second-Level Heading

### Third-Level Heading
```

**Discouraged** (Setext-style, though not linted):

```markdown
Top-Level Heading
=================

Second-Level Heading
--------------------
```

**Rationale**: Rule MD003 (heading-style) is disabled for Prettier compatibility. Prettier will normalize heading styles automatically when formatting.

### Blank Lines

Include blank lines before and after headings, code blocks, and lists.

**Good**:

```markdown
Some paragraph text.

## New Section

Content starts here.

- List item one
- List item two

More content.
```

### Code Blocks

**Policy**: Always use fenced code blocks with language identifiers for syntax highlighting. Prettier handles fence character selection (backticks vs tildes).

**Good** (language identifier required):

````markdown
```powershell
Get-ChildItem -Path $Directory
```

```bash
ls -la /path/to/directory
```

```yaml
name: Workflow
on: push
```
````

**Avoid** (missing language identifier):

````markdown
```
Get-ChildItem -Path $Directory
```
````

**Rationale**: Rule MD048 (code-fence-style) is disabled for Prettier compatibility, so fence character choice (backticks vs tildes) is not enforced. However, MD040 (fenced-code-language) remains enabled to require language identifiers for syntax highlighting.

### List Style

Use dashes (`-`) for unordered lists. Use sequential numbers for ordered lists.

**Good**:

```markdown
- First unordered item
- Second unordered item

1. First ordered item
2. Second ordered item
3. Third ordered item
```

### Emphasis

**Policy**: Prettier handles emphasis and strong emphasis style formatting. Asterisks (`*`) are preferred but not enforced by linting.

**Preferred**:

```markdown
This is *italic* and this is **bold**.
```

**Acceptable** (Prettier-formatted):

```markdown
This is _italic_ and this is __bold__.
```

**Rationale**: Rules MD049 (emphasis-style) and MD050 (strong-style) are disabled for Prettier compatibility. Prettier will normalize emphasis styles automatically when formatting.

### Tables

Use tables for structured data. Align columns for readability.

**Good**:

```markdown
| Agent | Purpose | When to Use |
|-------|---------|-------------|
| orchestrator | Task coordination | Complex multi-step tasks |
| implementer | Code execution | Production code, tests |
```

### Line Length

Line length is not enforced (MD013 disabled) to accommodate agent templates with long tool lists. However, keep paragraphs readable and break long lines where natural.

## Security Requirements

### Input Validation

Validate all external inputs before use. Never trust user-provided data.

**Good example** (PowerShell):

```powershell
if (-not (Test-Path -Path $InputPath -PathType Leaf)) {
    Write-Error "Invalid file path: $InputPath"
    return
}

# Validate path is within expected directory
$ResolvedPath = (Resolve-Path $InputPath).Path
if (-not $ResolvedPath.StartsWith($AllowedBaseDir)) {
    Write-Error "Path traversal attempt detected"
    return
}
```

**Good example** (Bash):

```bash
# Validate input is not empty
if [[ -z "$INPUT_VAR" ]]; then
    echo "Error: INPUT_VAR is required" >&2
    exit 1
fi

# Sanitize input before use in commands
SAFE_INPUT=$(printf '%q' "$INPUT_VAR")
```

### Command Injection Prevention

Never use unquoted variables in commands. Always quote variables and use parameter arrays.

**Good example** (PowerShell):

```powershell
# Use parameter splatting or arrays
$params = @{
    Path = $UserProvidedPath
    Force = $true
}
Copy-Item @params
```

**Avoid** (PowerShell):

```powershell
# Wrong: Unquoted variable allows injection
Invoke-Expression "Get-Content $UserInput"

# Wrong: Direct variable in string
& cmd /c "process $UserData"
```

**Good example** (Bash):

```bash
# Always quote variables
cp "$source_file" "$dest_file"

# Use arrays for command arguments
args=("$file1" "$file2")
command "${args[@]}"
```

**Avoid** (Bash):

```bash
# Wrong: Unquoted variables
cp $source_file $dest_file

# Wrong: Using eval with user input
eval $user_command
```

### Secure String Handling

Never log or display sensitive data such as tokens, passwords, or API keys.

**Good example**:

```powershell
# Mask sensitive data in logs
Write-Verbose "Authenticating with token: ***"

# Use SecureString for passwords
$SecurePassword = Read-Host -AsSecureString
```

**Avoid**:

```powershell
# Wrong: Logging secrets
Write-Host "Using token: $env:API_TOKEN"

# Wrong: Storing secrets in plain text
$Password = "mysecretpassword"
```

### File Path Security

Validate file paths to prevent path traversal attacks (CWE-22).

**Good example**:

```powershell
$NormalizedPath = [System.IO.Path]::GetFullPath($UserPath)
$AllowedBase = [System.IO.Path]::GetFullPath($BaseDirectory)

if (-not $NormalizedPath.StartsWith($AllowedBase)) {
    throw "Access denied: path outside allowed directory"
}
```

## Git Commit Conventions

### Commit Message Format

Use conventional commit format with type, optional scope, and description.

```text
<type>(<scope>): <short description>

<optional body>

<optional footer>
```

### Commit Types

| Type | Purpose |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change without feature/fix |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks |

### Examples

```text
feat(workflow): add parallel AI review execution

fix(security): prevent code injection via PR title

docs(agents): update orchestrator handoff protocol

refactor(scripts): extract common installation functions

test(mcp): add Sync-McpConfig transformation tests
```

### AI-Generated Commits

For AI-generated commits, include the signature line:

```text
feat(agents): implement skill extraction workflow

Added retrospective agent with skill scoring and deduplication.

[AI-generated with Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Agent Protocol Patterns

### Session Logs

Session logs MUST be created at `.agents/sessions/YYYY-MM-DD-session-NN.md` where `NN` is a zero-padded sequential number for that day.

**Good**: `.agents/sessions/2025-12-18-session-01.md`

### Handoff Document

The handoff document at `.agents/HANDOFF.md` MUST be updated at session end with:

- Session summary
- Link to session log
- Changes made
- Next steps

### RFC 2119 Keywords

Use RFC 2119 keywords consistently for requirements:

| Keyword | Meaning |
|---------|---------|
| MUST | Absolute requirement, violation is protocol failure |
| SHOULD | Recommended, but exceptions may exist with documented rationale |
| MAY | Truly optional, no documentation required if omitted |

**Good**:

```markdown
Agents MUST read `.agents/HANDOFF.md` before starting work.

Agents SHOULD search relevant memories for prior decisions.

Agents MAY include implementation notes in the session log.
```

### Memory Storage

Serena memories are stored in `.serena/memories/` with descriptive filenames. When Serena MCP is available, access memories using `mcp__serena__read_memory` with just the memory name (without path or extension).

**Good examples**:

- `skills-implementation` (access via `mcp__serena__read_memory` with `memory_file_name="skills-implementation"`) and stored on disk at `.serena/memories/skills-implementation.md`
- `skills-github-cli` (access via `mcp__serena__read_memory` with `memory_file_name="skills-github-cli"`) and stored on disk at `.serena/memories/skills-github-cli.md`
- `retrospective-2025-12-18-ai-workflow` (access via `mcp__serena__read_memory` with `memory_file_name="retrospective-2025-12-18-ai-workflow"`) and stored on disk at `.serena/memories/retrospective-2025-12-18-ai-workflow.md`

## Documentation Standards

### ADR Format

Architecture Decision Records follow the pattern `ADR-NNN-kebab-case-title.md` with three-digit zero-padded numbers.

**Good**: `ADR-005-use-pkce-for-oauth.md`

ADRs must include:

- Status (Proposed, Accepted, Deprecated, Superseded)
- Context (problem being addressed)
- Decision (what was decided)
- Consequences (tradeoffs and implications)

### Artifact Naming

All sequenced artifacts use three-digit zero-padded numbers:

| Artifact | Pattern | Example |
|----------|---------|---------|
| EPIC | `EPIC-NNN-kebab-case.md` | `EPIC-001-user-authentication.md` |
| ADR | `ADR-NNN-kebab-case.md` | `ADR-005-oauth-flow.md` |
| Plan | `NNN-kebab-case-plan.md` | `001-authentication-plan.md` |
| REQ | `REQ-NNN-kebab-case.md` | `REQ-001-login-flow.md` |
| TASK | `TASK-NNN-kebab-case.md` | `TASK-001-implement-login.md` |

### Cross-References

Use relative paths for cross-references within the repository. Never use absolute paths that include machine-specific directories.

**Good**:

```markdown
See [naming conventions](../governance/naming-conventions.md)
```

**Avoid**:

```markdown
See [naming conventions](D:\src\GitHub\repo\.agents\governance\naming-conventions.md)
```

### Examples in Documentation

Include both good and bad examples when documenting patterns. Use code blocks with appropriate language identifiers.

## Bash Script Standards

### Shell Declaration

Always start bash scripts with a shebang and set strict mode.

**Good**:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

### Bash Function Naming

Use snake_case for function names in bash scripts.

**Good**:

```bash
function get_pr_diff() {
    local pr_number="$1"
    gh pr diff "$pr_number"
}

function validate_input() {
    if [[ -z "${1:-}" ]]; then
        echo "Error: argument required" >&2
        return 1
    fi
}
```

### Variable Naming

Use UPPER_CASE for environment variables and exported variables. Use lower_case for local variables.

**Good**:

```bash
export COPILOT_GITHUB_TOKEN="$token"

local file_path="$1"
local line_count=0
```

### Quoting

Always quote variables to prevent word splitting and globbing issues.

**Good**:

```bash
if [[ -f "$file_path" ]]; then
    content=$(cat "$file_path")
fi
```

**Avoid**:

```bash
if [[ -f $file_path ]]; then    # Wrong: unquoted variable
    content=$(cat $file_path)    # Wrong: unquoted variable
fi
```

## GitHub Actions Standards

### Shell Interpolation

Use environment variables instead of direct `${{ }}` interpolation in shell scripts to prevent injection attacks.

**Good**:

```yaml
- name: Process input
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: |
    # Use the env var safely in shell
    echo "Processing: $PR_TITLE"
```

**Avoid**:

```yaml
- name: Process input
  run: |
    # Wrong: direct interpolation vulnerable to injection
    echo "Processing: ${{ github.event.pull_request.title }}"
```

### Multi-line Outputs

Use heredoc syntax for multi-line GITHUB_OUTPUT content.

**Good**:

```yaml
- name: Set output
  id: result
  run: |
    {
      echo "content<<EOF"
      echo "Line 1"
      echo "Line 2"
      echo "EOF"
    } >> "$GITHUB_OUTPUT"
```

### Artifact Usage

Use artifacts instead of job outputs for passing data between matrix jobs.

**Good**:

```yaml
jobs:
  build:
    strategy:
      matrix:
        component: [a, b, c]
    steps:
      - name: Build
        run: echo "result" > result-${{ matrix.component }}.txt
      - uses: actions/upload-artifact@v4
        with:
          name: results-${{ matrix.component }}
          path: result-${{ matrix.component }}.txt

  aggregate:
    needs: build
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: results-*
          merge-multiple: true
```

## Testing Standards

### Pester Tests

PowerShell tests use Pester framework. Tests should be located alongside source files in a `tests` directory.

**Naming**: `<ScriptName>.Tests.ps1`

**Structure**:

```powershell
Describe "Function-Name" {
    Context "When condition" {
        It "Should expected behavior" {
            # Arrange
            $input = "test"

            # Act
            $result = Function-Name -Input $input

            # Assert
            $result | Should -Be "expected"
        }
    }
}
```

### Test Coverage

Aim for 80% or higher test coverage for PowerShell scripts. Critical security functions require 100% coverage.

## Version Control

### Branch Naming

Use descriptive branch names with type prefix.

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/description` | `feat/ai-agent-workflow` |
| Fix | `fix/description` | `fix/security-injection` |
| Documentation | `docs/description` | `docs/copilot-setup` |
| Refactor | `refactor/description` | `refactor/common-module` |

### Pull Request Requirements

PRs should include:

- Descriptive title following conventional commit format
- Summary of changes
- Link to related issues
- Test plan or verification steps

## Code Review Focus Areas

When reviewing code, prioritize these areas:

1. **Security**: Input validation, injection prevention, secret handling
2. **Correctness**: Logic errors, edge cases, error handling
3. **Maintainability**: Naming, documentation, code organization
4. **Performance**: Efficiency, resource usage
5. **Consistency**: Adherence to style guide patterns

## Additional Resources

- [Session Protocol](.agents/SESSION-PROTOCOL.md) - Session management requirements
- [Naming Conventions](.agents/governance/naming-conventions.md) - Artifact naming patterns
- [Agent Catalog](AGENTS.md) - Complete agent documentation
