# AI Agents Scripts

PowerShell scripts for the AI Agents system.

## Script Organization

Scripts are organized by **intended audience and execution context**:

- **`scripts/`** - Developer-facing utilities (manual + pre-commit hooks)
- **`.github/scripts/`** - CI/CD automation (GitHub Actions only, not for direct use)
- **`build/scripts/`** - Build system automation
- **`.claude/skills/`** - AI agent skills (internal implementation, wrapped for developer use)
- **`tests/`** - Pester test files (root-level, not under scripts/)

**When to use each location**:

- Creating a tool for developers to run? -> `scripts/`
- Building a GitHub Actions workflow helper? -> `.github/scripts/`
- Adding AI agent capability? -> `.claude/skills/` (with wrapper in `scripts/` if needed)
- Writing tests? -> `tests/`

See [ADR-019](../.agents/architecture/ADR-019-script-organization.md) for detailed rationale and guidelines.

## Installation

For installing agents to Claude Code, VS Code, or Copilot CLI, use [skill-installer](https://github.com/rjmurillo/skill-installer):

```bash
uvx --from git+https://github.com/rjmurillo/skill-installer skill-installer interactive
```

See [docs/installation.md](../docs/installation.md) for complete installation documentation.

## Validation Scripts

The repository includes validation scripts for enforcing protocol compliance and code quality. These implement the technical guardrails from Issue #230.

### Session Protocol Validation

#### validate_session_json.py

Validates session protocol compliance for session logs.

**Usage**:

```bash
# Validate specific session
python3 scripts/validate_session_json.py .agents/sessions/2025-12-17-session-01.json

# Validate with pre-commit mode
python3 scripts/validate_session_json.py .agents/sessions/2025-12-17-session-01.json --pre-commit
```

**Called By**: Pre-commit hook, orchestrator, CI

### PR and Code Quality

#### Validate-PRDescription.ps1

Validates PR description matches actual code changes (prevents Analyst CRITICAL_FAIL).

**Usage**:

```powershell
.\scripts\Validate-PRDescription.ps1 -PRNumber 226 -CI
```

**Called By**: CI workflow (`.github/workflows/pr-validation.yml`)

#### detect_skill_violation.py

Detects raw `gh` command usage when GitHub skills exist (WARNING, non-blocking).

**Usage**:

```bash
# Run skill violation detection
python3 scripts/detect_skill_violation.py
```

**Called By**: Pre-commit hook (via New-PR.ps1)

#### Detect-TestCoverageGaps.ps1

Detects PowerShell files without corresponding test files (WARNING, non-blocking).

**Usage**:

```powershell
# Check staged files
.\scripts\Detect-TestCoverageGaps.ps1 -StagedOnly

# Check with ignore file
.\scripts\Detect-TestCoverageGaps.ps1 -IgnoreFile ".testignore"
```

**Called By**: Pre-commit hook

### PR Creation

#### New-ValidatedPR.ps1

Creates a PR with all guardrails enforced.

**Usage**:

```powershell
# Normal PR (runs validations)
.\scripts\New-ValidatedPR.ps1 -Title "feat: Add feature" -Body "Description"

# Draft PR
.\scripts\New-ValidatedPR.ps1 -Title "WIP: Feature" -Draft

# Force mode (creates audit trail)
.\scripts\New-ValidatedPR.ps1 -Title "hotfix" -Force

# Interactive mode
.\scripts\New-ValidatedPR.ps1 -Web
```

#### validate_workflows.py

Validates GitHub Actions workflows locally before pushing (ADR-006 compliance).

**Usage**:

```bash
# Validate all workflows
python3 scripts/validate_workflows.py

# Validate only changed files
python3 scripts/validate_workflows.py --changed

# Validate specific file
python3 scripts/validate_workflows.py .github/workflows/pytest.yml

# Run with act (if installed)
python3 scripts/validate_workflows.py --act
```

**Validates**:

- YAML syntax correctness
- Workflow structure (name, on, jobs)
- Action SHA pinning (security requirement)
- Workflow size (ADR-006: warns if >100 lines)
- Concurrency configuration
- Explicit permissions (security best practice)

**Exit Codes**:

- `0`: All validations passed (warnings are OK)
- `1`: Validation errors found (must fix)
- `2`: Script error (missing dependencies)

See [docs/WORKFLOW-VALIDATION.md](../docs/WORKFLOW-VALIDATION.md) for complete documentation.

### Other Validation Scripts

- `Validate-Consistency.ps1` - Cross-document consistency
- `Sync-McpConfig.ps1` - MCP configuration sync
- `check_skill_exists.py` - Skill availability check
- `Invoke-BatchPRReview.ps1` - Batch PR review automation

#### Sync-McpConfig.ps1

Syncs MCP configuration from Claude Code's `.mcp.json` to Factory Droid and VS Code formats.

**Usage**:

```powershell
# Sync to VS Code (default behavior)
.\scripts\Sync-McpConfig.ps1

# Sync to Factory Droid
.\scripts\Sync-McpConfig.ps1 -Target factory

# Sync to both Factory and VS Code
.\scripts\Sync-McpConfig.ps1 -SyncAll

# Check what would change without making changes
.\scripts\Sync-McpConfig.ps1 -WhatIf

# Return boolean indicating whether sync occurred
$synced = .\scripts\Sync-McpConfig.ps1 -PassThru
if ($synced) { Write-Host "Configuration was synced" }
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-SourcePath` | String | `.mcp.json` | Source Claude .mcp.json path |
| `-DestinationPath` | String | Auto-detected | Custom destination path (not used with SyncAll) |
| `-Target` | String | `vscode` | `vscode` or `factory` (mutually exclusive with SyncAll) |
| `-SyncAll` | Switch | `$false` | Generate both Factory and VS Code configs |
| `-Force` | Switch | `$false` | Overwrite even if content identical |
| `-WhatIf` | Switch | `$false` | Show what would change without making changes |
| `-PassThru` | Switch | `$false` | Return `$true` if files synced, `$false` otherwise |

**Output Formats**:

- Factory (`.factory/mcp.json`): Uses `mcpServers` root key (same as Claude)
- VS Code (`.vscode/mcp.json`): Uses `servers` root key, transforms serena config

**Note**: This script generates `.factory/mcp.json` for Factory Droid compatibility. For more information on Factory Droid MCP configuration, see <https://docs.factory.ai/cli/configuration/mcp>

See [docs/technical-guardrails.md](../docs/technical-guardrails.md) for complete validation documentation.

## Running Tests

Requires [Pester](https://pester.dev/) 5.x:

```powershell
# Install Pester
Install-Module -Name Pester -Force -Scope CurrentUser

# Run all tests
Invoke-Pester -Path .\tests

# Run specific test file
Invoke-Pester -Path .\tests\Validate-SessionJson.Tests.ps1

# Run with detailed output
Invoke-Pester -Path .\tests -Output Detailed
```

## Full Documentation

See [docs/installation.md](../docs/installation.md) for complete installation documentation.

See [docs/technical-guardrails.md](../docs/technical-guardrails.md) for validation and guardrail documentation.
