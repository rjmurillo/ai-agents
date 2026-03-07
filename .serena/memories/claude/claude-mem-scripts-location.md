# Claude-Mem Export/Import Scripts Location

## Summary

The claude-mem plugin provides export/import functionality via TypeScript scripts. The ai-agents project wraps these with PowerShell scripts for ADR-005 compliance and consistent interface.

## Script Locations

### Installed Plugin Scripts (Source)

- **export-memories.ts**: `~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts`
- **import-memories.ts**: `~/.claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts`

These are the actual implementation scripts installed with the claude-mem plugin.

### Project PowerShell Wrappers (ai-agents)

- **Export-ClaudeMemMemories.ps1**: `.claude-mem/scripts/Export-ClaudeMemMemories.ps1`
- **Import-ClaudeMemMemories.ps1**: `.claude-mem/scripts/Import-ClaudeMemMemories.ps1`

These PowerShell scripts call the plugin scripts directly and provide:
- ADR-005 compliance (PowerShell-only)
- Consistent parameter interface
- Security review integration
- Idempotent import

## Wrapper Implementation

```powershell
#!/usr/bin/env pwsh
# Export wrapper
$PluginScript = Join-Path $env:HOME '.claude' 'plugins' 'marketplaces' 'thedotmack' 'scripts' 'export-memories.ts'

npx tsx $PluginScript $Query $OutputFile
```

## Why PowerShell Wrappers

1. **ADR-005 Compliance**: Project uses PowerShell-only for scripting
2. **Parameter Interface**: Named parameters (`-Query`, `-Topic`) vs positional
3. **Security Integration**: Reminds to run security review script
4. **Consistent UX**: Matches other project PowerShell scripts
5. **Documentation Clarity**: Clear parameter names vs positional args

## Usage Examples

All commands work from project root:

```bash
# Export session memories
pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "session 229" -SessionNumber 229 -Topic "frustrations"

# Import all memories
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1

# Security review (REQUIRED before commit)
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile .claude-mem/memories/2026-01-03-session-229-frustrations.json
```

## Source Repository

The original TypeScript scripts are part of the claude-mem plugin:
- **GitHub**: https://github.com/thedotmack/claude-mem/tree/main/scripts
- **Documentation**: https://docs.claude-mem.ai/usage/export-import

## Integration Points

- `.claude-mem/memories/README.md` - Documents PowerShell wrapper usage
- `.claude-mem/memories/AGENTS.md` - Agent instructions for export/import
- `.agents/governance/MEMORY-MANAGEMENT.md` - Three-tier memory architecture
- `.agents/SESSION-PROTOCOL.md` - Session start/end requirements

## Troubleshooting

### "Plugin script not found"

Verify plugin installation:
```bash
Test-Path ~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts
```

If missing, reinstall claude-mem plugin.

### Logger initialization errors

Non-fatal warnings from plugin script. Exports/imports still complete successfully.

### Security review failures

Run security review script:
```bash
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile [file].json
```

If sensitive data detected, manually redact before committing.

## Session Context

- **Created**: January 3, 2026 (Session 229)
- **Updated**: January 3, 2026 (Session 230 - PowerShell migration)
- **Reason**: User questioned wrapper complexity; replaced TypeScript wrappers with PowerShell for ADR-005 compliance

## Related

- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
- [claude-flow-research-2025-12-20](claude-flow-research-2025-12-20.md)
