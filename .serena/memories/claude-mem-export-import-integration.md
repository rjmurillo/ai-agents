# Claude-Mem Export/Import Integration

## Summary

Integrated Claude-Mem's export/import functionality into operational procedures to enable memory sharing across team members and installations.

## Changes Made

### Directory Structure

Created `.claude-mem/memories/` with three components:

- `README.md` - Comprehensive export/import workflow documentation
- `exports/` - Session-exported memories (committed to git)
- `imports/` - Staging area for received memories (gitignored)
- `.gitignore` - Excludes imports/*.json, keeps exports/*.json

### SESSION-PROTOCOL.md Updates

**Phase 2.1: Import Shared Memories (RECOMMENDED)** - Added to Session Start:

- Check `.claude-mem/memories/imports/` for new files
- Import: `npx tsx scripts/import-memories.ts [file].json`
- Document import count in session log
- Automatic duplicate prevention via composite keys

**Phase 0.5: Export Session Memories (RECOMMENDED)** - Added to Session End:

- Export to `.claude-mem/memories/exports/` with naming convention
- Privacy review checklist (API keys, tokens, paths, PII)
- Session-specific naming: `YYYY-MM-DD-session-NNN-topic.json`
- Document export path in session log

### MEMORY-MANAGEMENT.md (New)

Comprehensive governance document created at `.agents/governance/MEMORY-MANAGEMENT.md`:

- Three-tier memory architecture (Serena, Forgetful, Claude-Mem)
- Memory system selection guide
- Session workflow integration
- Export/import detailed commands
- Privacy review process
- Team collaboration workflows
- Onboarding procedures
- Troubleshooting guide

### CLAUDE.md Updates

Added Claude-Mem section to MCP Servers:

- Quick reference for export/import commands
- Workflow integration summary
- Links to detailed documentation

Updated MCP server count from three to four.

## Export/Import Workflow

### Session Start

```bash
# Import shared memories
npx tsx scripts/import-memories.ts .claude-mem/memories/imports/[file].json
```

### Session End

```bash
# Export by session number
npx tsx scripts/export-memories.ts "session NNN" \
  .claude-mem/memories/exports/YYYY-MM-DD-session-NNN-topic.json

# Privacy review
grep -i "api_key|password|token|secret" [export-file].json

# Commit to git
git add .claude-mem/memories/exports/[file].json
```

## Naming Conventions

- Session exports: `YYYY-MM-DD-session-NNN-topic.json`
- Thematic exports: `YYYY-MM-DD-theme.json`
- Onboarding sets: `onboarding-YYYY-MM-DD.json`

## Integration Points

### Agents

- **All agents**: SHOULD export memories for significant sessions
- **All agents**: SHOULD import shared memories at session start

### Protocol

- SESSION-PROTOCOL.md: Added Phase 2.1 (import) and Phase 0.5 (export)
- Session log template: Updated checklists with import/export steps

### Git

- Exports committed to version control for sharing
- Imports gitignored (staging area only)
- Privacy review required before commit

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

### Privacy Review Checklist

Before committing exports, verify NO sensitive data:

- API keys, tokens, passwords
- Private file paths or system information
- Confidential business logic
- Personal identifying information

## Team Collaboration Use Cases

1. **Sharing learnings**: Export session memories, commit to git, teammates import
2. **Onboarding**: Bulk export all project memories, new members import on setup
3. **Cross-session context**: Export after significant sessions, import at session start
4. **Disaster recovery**: Restore memories from git history

## References

- Documentation: https://docs.claude-mem.ai/usage/export-import
- .claude-mem/memories/README.md - Detailed workflow
- .agents/governance/MEMORY-MANAGEMENT.md - Complete memory strategy
- SESSION-PROTOCOL.md - Session start/end requirements
- ADR-007 - Memory-First Architecture

## Session Context

Session 229 - January 3, 2026
Files modified:
- .agents/SESSION-PROTOCOL.md (Phase 2.1, Phase 0.5)
- CLAUDE.md (Claude-Mem section)
- .agents/governance/MEMORY-MANAGEMENT.md (new)
- .claude-mem/ directory structure (new)
