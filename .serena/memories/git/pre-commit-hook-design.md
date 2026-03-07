# Pre-Commit Hook Design Patterns

## Key Decisions (ADR-004)

The pre-commit hook serves as the validation orchestration point for:

1. **Markdown linting** - BLOCKING with auto-fix
2. **Planning validation** - WARNING only
3. **Consistency validation** - WARNING only  
4. **Security detection** - WARNING only
5. **MCP config sync** - AUTO-FIX (stages mcp.json)

## Design Principles

- **Fail-fast for critical issues** (invalid JSON, syntax errors)
- **Warn-only for advisory** (planning, security)
- **Auto-fix when deterministic** (markdown lint, config transforms)
- **Security-hardened** (symlink rejection, path validation)

## When to Add New Validations

**Pre-commit** (preferred):

- Fast execution (<2s)
- Local-only (no network)
- Auto-fixable or warning-only
- Non-destructive

**CI instead**:

- Slow or network-dependent
- Complex analysis
- Security-sensitive operations

## Implementation Checklist

- [ ] Use `-NoProfile` with pwsh
- [ ] Reject symlinks (MEDIUM-002)
- [ ] Validate paths exist
- [ ] Quote all variables
- [ ] Use `--` separator for arguments
- [ ] Choose blocking level (BLOCKING/WARNING/AUTO-FIX)

## Related Files

- `.githooks/pre-commit` - Main hook implementation
- `.agents/architecture/ADR-004-pre-commit-hook-architecture.md` - Full decision record
- `scripts/Sync-McpConfig.ps1` - MCP config sync script

## MCP Config Sync

Transform Claude's `.mcp.json` to VS Code's `mcp.json`:

- Claude: `{ "mcpServers": {...} }`  
- VS Code: `{ "servers": {...} }`

Source of truth: `.mcp.json` (Claude format)
