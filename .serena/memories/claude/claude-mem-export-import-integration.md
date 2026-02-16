# Claude-Mem Export/Import Integration

## Summary

Integrated Claude-Mem's export/import functionality into operational procedures using PowerShell wrappers to enable memory sharing across team members and installations while maintaining ADR-005 compliance.

## Changes Made (Updated Jan 3, 2026)

### Directory Structure

Created `.claude-mem/` with flat structure:

- `memories/` - All exported JSON files (committed to git)
  - `README.md` - Comprehensive export/import workflow documentation
  - `AGENTS.md` - Agent-specific instructions
  - `*.json` - Memory snapshots (flat, no subdirectories)
- `scripts/` - PowerShell wrapper scripts
  - `Export-ClaudeMemMemories.ps1` - Export wrapper with named parameters
  - `Import-ClaudeMemMemories.ps1` - Import wrapper (idempotent)
- `.gitignore` - Minimal (only temp files)

### SESSION-PROTOCOL.md Updates

**Phase 2.1: Import Shared Memories (RECOMMENDED)** - Session Start:

- Import all `.json` files from `.claude-mem/memories/`
- Command: `pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1`
- Document import count in session log
- Automatic duplicate prevention via composite keys

**Phase 0.5: Export Session Memories (RECOMMENDED)** - Session End:

- Export to `.claude-mem/memories/` with naming convention
- Command: `pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "[query]" -SessionNumber NNN -Topic "topic"`
- Security review checklist (API keys, tokens, paths, PII)
- Session-specific naming: `YYYY-MM-DD-session-NNN-topic.json`
- Document export path in session log

### MEMORY-MANAGEMENT.md

Updated comprehensive governance document at `.agents/governance/MEMORY-MANAGEMENT.md`:

- Three-tier memory architecture (Serena, Forgetful, Claude-Mem)
- Memory system selection guide
- Session workflow integration
- PowerShell command examples
- Flat directory structure
- Privacy review process
- Team collaboration workflows
- Onboarding procedures
- Troubleshooting guide

### CLAUDE.md Updates

Updated Claude-Mem section in MCP Servers:

- PowerShell script references
- Flat directory structure
- Security review as REQUIRED
- Links to detailed documentation

### PowerShell Script Implementation

Created two PowerShell scripts in `.claude-mem/scripts/`:

**Export-ClaudeMemMemories.ps1**:
- Named parameters: `-Query`, `-SessionNumber`, `-Topic`, `-OutputFile`
- Calls plugin script at `~/.claude/plugins/marketplaces/thedotmack/scripts/export-memories.ts`
- Generates default filename: `YYYY-MM-DD-session-NNN-topic.json`
- Reminds user to run security review

**Import-ClaudeMemMemories.ps1**:
- No parameters required (processes all `.json` files)
- Idempotent (safe to run multiple times)
- Calls plugin script for each file
- Reports import count

## Export/Import Workflow

### Session Start

```bash
# Import all shared memories (idempotent)
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1
```

Output:
```
🔄 Importing N memory file(s) from .claude-mem/memories/
  📁 file1.json
  📁 file2.json
✅ Import complete: N file(s) processed
   Duplicates automatically skipped via composite key matching
```

### Session End

```bash
# Export by session number and topic
pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "session 229" -SessionNumber 229 -Topic "frustrations"

# Security review (REQUIRED)
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile .claude-mem/memories/2026-01-03-session-229-frustrations.json

# Commit if clean
git add .claude-mem/memories/2026-01-03-session-229-frustrations.json
git commit -m "docs(memory): export session 229 learnings - agent frustrations"
```

## Naming Conventions

- Session exports: `YYYY-MM-DD-session-NNN-topic.json`
- Thematic exports: `YYYY-MM-DD-topic.json`
- All files directly in `.claude-mem/memories/` (no subdirectories)

## Integration Points

### Agents

- **All agents**: SHOULD export memories for significant sessions
- **All agents**: SHOULD import shared memories at session start
- **All agents**: MUST run security review before committing exports

### Protocol

- SESSION-PROTOCOL.md: Phase 2.1 (import) and Phase 0.5 (export)
- Session log template: Import/export checklists with verification
- Security review as BLOCKING gate

### Scripts

- `.claude-mem/scripts/Export-ClaudeMemMemories.ps1` - PowerShell export wrapper
- `.claude-mem/scripts/Import-ClaudeMemMemories.ps1` - PowerShell import wrapper
- `scripts/Review-MemoryExportSecurity.ps1` - Security scanner (6 pattern categories)

### Git

- All `.json` files committed to version control for sharing
- Security review prevents credential exposure
- Flat structure simplifies git operations

## Key Features

### Duplicate Prevention

Claude-Mem automatically prevents duplicate imports using composite keys:

| Record Type | Detection Key |
|-------------|---------------|
| Sessions | `claude_session_id` |
| Summaries | `sdk_session_id` |
| Observations | `sdk_session_id` + `title` + `created_at_epoch` |
| Prompts | `claude_session_id` + `prompt_number` |

Safe to reimport the same file multiple times.

### Security Review (BLOCKING)

PowerShell script scans for sensitive patterns:

- API Keys/Tokens: `api[_-]?key`, `access[_-]?token`, `github[_-]?token`
- Passwords/Secrets: `password`, `secret`, `credential`
- Private Keys: `BEGIN (RSA|PRIVATE|ENCRYPTED) KEY`
- File Paths: `/home/[a-z]+/`, `C:\Users\[^\]+\`
- Database Credentials: `connection[_-]?string`, `jdbc:`, `mongodb://`
- Email/PII: Email regex, SSN patterns

Exit code 0 = clean, 1 = sensitive data found (blocks commit)

### ADR-005 Compliance

PowerShell-only scripting enforced:
- Removed TypeScript wrapper scripts from `scripts/`
- Created PowerShell wrappers in `.claude-mem/scripts/`
- PowerShell calls plugin TypeScript scripts directly
- Consistent with project scripting standards

## Team Collaboration Use Cases

1. **Sharing learnings**: Export session memories, commit to git, teammates import
2. **Onboarding**: Export project memories, new members import on setup
3. **Cross-session context**: Export after significant sessions, import at session start
4. **Disaster recovery**: Restore memories from git history

## References

- Documentation: https://docs.claude-mem.ai/usage/export-import
- `.claude-mem/memories/README.md` - Detailed workflow
- `.claude-mem/memories/AGENTS.md` - Agent instructions
- `.agents/governance/MEMORY-MANAGEMENT.md` - Complete memory strategy
- `.agents/SESSION-PROTOCOL.md` - Session start/end requirements
- ADR-007 - Memory-First Architecture
- ADR-005 - PowerShell-Only Scripting

## Session Context

**Created**: Session 229 - January 3, 2026
**Updated**: Session 230 - January 3, 2026 (PowerShell migration)

Files modified:
- `.agents/SESSION-PROTOCOL.md` (Phase 2.1, Phase 0.5)
- `CLAUDE.md` (Claude-Mem section)
- `.agents/governance/MEMORY-MANAGEMENT.md` (PowerShell updates)
- `.claude-mem/scripts/Export-ClaudeMemMemories.ps1` (new)
- `.claude-mem/scripts/Import-ClaudeMemMemories.ps1` (new)
- `.claude-mem/.gitignore` (simplified)
- `.claude-mem/memories/README.md` (PowerShell updates)
- `.claude-mem/memories/AGENTS.md` (PowerShell updates)
- `scripts/Review-MemoryExportSecurity.ps1` (new)

Files removed:
- scripts/export-memories.ts (removed) (TypeScript wrapper)
- scripts/import-memories.ts (removed) (TypeScript wrapper)
- `.claude-mem/scripts/Import-ClaudeMemMemories.ps1` (moved to `.claude-mem/scripts/`)

## Related

- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
- [claude-flow-research-2025-12-20](claude-flow-research-2025-12-20.md)
