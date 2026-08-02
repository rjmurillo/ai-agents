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

For installing agents to Claude Code, Copilot CLI, VS Code, or Visual Studio, use each tool's native marketplace or repository-level integration.

- Claude Code: `/install-plugin rjmurillo/ai-agents`
- Copilot CLI: `/plugin marketplace add rjmurillo/ai-agents` then `/plugin install project-toolkit@ai-agents`
- VS Code / Visual Studio: open the repository so `.github/agents/` and `.github/copilot-instructions.md` load automatically

See [docs/installation.md](../docs/installation.md) for complete installation documentation.

## Validation Scripts

The repository includes validation scripts for enforcing protocol compliance and code quality. These implement the technical guardrails from Issue #230.

### Session Protocol Validation

#### validate_session_json.py

Validates session protocol compliance for session logs.

**Usage**:

```bash
# Validate specific session
uv run python scripts/validate_session_json.py .agents/sessions/2025-12-17-session-01.json

# Validate with pre-commit mode
uv run python scripts/validate_session_json.py .agents/sessions/2025-12-17-session-01.json --pre-commit
```

**Called By**: Pre-commit hook, orchestrator, CI

### PR and Code Quality

#### pr_description.py

Validates PR description matches actual code changes (prevents Analyst CRITICAL_FAIL).

**Usage**:

```bash
python3 scripts/validation/pr_description.py --pr-number 226 --ci
```

**Called By**: CI workflow (`.github/workflows/pr-validation.yml`)

#### detect_skill_violation.py

Detects raw `gh` command usage when GitHub skills exist (WARNING, non-blocking).

**Usage**:

```bash
# Run skill violation detection
python3 scripts/detect_skill_violation.py
```

**Called By**: Pre-commit hook (via new_pr.py)

#### detect_test_coverage_gaps.py

Detects script files without corresponding test files (WARNING, non-blocking).

**Usage**:

```bash
# Check staged files
uv run --frozen python -m scripts.detect_test_coverage_gaps --staged-only

# Check with ignore file
uv run --frozen python -m scripts.detect_test_coverage_gaps --ignore-file ".testignore"
```

**Called By**: Pre-commit hook

### PR Creation

#### new_validated_pr.py

Creates a PR with all guardrails enforced.

**Usage**:

```bash
# Normal PR (runs validations)
uv run --frozen python -m scripts.new_validated_pr --title "feat: Add feature" --body "Description"

# Draft PR
uv run --frozen python -m scripts.new_validated_pr --title "WIP: Feature" --draft

# Force mode (creates audit trail)
uv run --frozen python -m scripts.new_validated_pr --title "hotfix" --skip-validation --audit-reason "hotfix"

# Interactive mode
uv run --frozen python -m scripts.new_validated_pr --web
```

#### validate_workflows.py

Validates GitHub Actions workflows locally before pushing (ADR-006 compliance).

**Usage**:

```bash
# Validate all workflows
uv run python scripts/validate_workflows.py

# Validate only changed files
uv run python scripts/validate_workflows.py --changed

# Validate specific file
uv run python scripts/validate_workflows.py .github/workflows/pytest.yml

# Run with act (if installed)
uv run python scripts/validate_workflows.py --act
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

- `scripts/validation/hook_contracts.py` - Hook registration contract checks, wired by Hook Contract Check
- `scripts/validation/traceability.py` - Spec link traceability, wired by pre-PR sequence step 10
- `sync_mcp_config.py` - MCP configuration sync
- `check_skill_exists.py` - Skill availability check
- `invoke_batch_pr_review.py` - Batch PR review automation

#### sync_mcp_config.py

Syncs MCP configuration from Claude Code's `.mcp.json` to Factory Droid and VS Code formats.

**Usage**:

```bash
# Sync to VS Code (default behavior)
.\scripts\sync_mcp_config.py

# Sync to Factory Droid
.\scripts\sync_mcp_config.py -Target factory

# Sync to both Factory and VS Code
.\scripts\sync_mcp_config.py -SyncAll

# Check what would change without making changes
.\scripts\sync_mcp_config.py -WhatIf

# Return boolean indicating whether sync occurred
$synced = .\scripts\sync_mcp_config.py -PassThru
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

## Keep-Disposition Script Entry Points

These scripts are retained for direct use. Each command below prints the
script-specific CLI help and validates the documented entry point.

| Script | Purpose | Invocation |
|--------|---------|------------|
| `scripts/compute_health_status.py` | Computes aggregate repository health from memory and session metrics. | `uv run python scripts/compute_health_status.py --help` |
| `scripts/consolidate_skills.py` | Finds recurring session-log patterns and emits skill candidates. | `uv run python scripts/consolidate_skills.py --help` |
| `scripts/maintenance/gc_worktrees.py` | Reports or removes stale git worktrees after safety checks. | `uv run python scripts/maintenance/gc_worktrees.py --help` |
| `scripts/new_validated_pr.py` | Creates a PR through the validated PR guardrail wrapper. | `uv run python scripts/new_validated_pr.py --help` |
| `scripts/openclaw_bridge.py` | Exports Claude agent definitions to an OpenClaw workspace or JSON. | `uv run python scripts/openclaw_bridge.py --help` |
| `scripts/split_bundled_skills.py` | Splits bundled skill files into individual skill memory files. | `uv run python scripts/split_bundled_skills.py --help` |
| `scripts/normalize_line_endings.py` | Normalizes repository line endings to LF through git renormalization. | `uv run python scripts/normalize_line_endings.py --help` |
| `scripts/traceability/reconstruct_trace.py` | Reconstructs multi-agent trace trees from session log correlation fields. | `uv run python scripts/traceability/reconstruct_trace.py --help` |

## Running Tests

Requires [Pester](https://pester.dev/) 5.x:

```bash
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
