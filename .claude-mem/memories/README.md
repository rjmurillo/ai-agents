# Claude-Mem Shared Memories

This directory contains exportable memory snapshots from the Claude-Mem MCP server for sharing across team members, installations, and sessions.

## Purpose

Claude-Mem memories are local to each installation. Export/import enables:

1. **Team collaboration** - Share learnings across developers
2. **Onboarding** - Bootstrap new installations with project knowledge
3. **Cross-session persistence** - Version control memories alongside code
4. **Disaster recovery** - Restore memories from git history

## Directory Structure

```text
.claude-mem/memories/
├── README.md                                          # This file
├── 2026-01-03-session-229-frustrations.json         # Memory snapshots
├── 2026-01-03-session-230-testing-philosophy.json
└── ...
```

All memory exports are stored in this single directory. Auto-import on session start handles idempotent loading.

## Export Workflow (Session End)

When ending a session, export memories created during that session:

```bash
# Export by topic/session
npx tsx scripts/export-memories.ts "session 229" .claude-mem/memories/2026-01-03-session-229.json

# Export by date range (using jq to filter)
npx tsx scripts/export-memories.ts "" all.json
cat all.json | jq '.observations | map(select(.created_at_epoch >= 1735862400))' > .claude-mem/memories/2026-01-03-filtered.json
rm all.json

# Export project-specific memories
npx tsx scripts/export-memories.ts "" .claude-mem/memories/2026-01-03-project.json --project=ai-agents
```

**Naming Convention**: `YYYY-MM-DD-session-NNN-topic.json`

**Note**: The `export-memories.ts` and `import-memories.ts` scripts are wrapper scripts located in the project's `scripts/` directory. They forward to the installed claude-mem plugin scripts at `~/.claude/plugins/marketplaces/thedotmack/scripts/`.

## Import Workflow (Session Start or Onboarding)

### Automatic Import (Session Start)

The auto-import script runs idempotently on session start:

```bash
# Automatically imports all .json files from .claude-mem/memories/
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1
```

**Session Protocol Integration**: Can be added to SessionStart hook for automatic execution.

### Manual Import

Import specific files or new memories from teammates:

```bash
# Import a specific file
npx tsx scripts/import-memories.ts .claude-mem/memories/shared-memories.json

# Import all files (same as auto-import script)
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1
```

## Duplicate Prevention

Claude-Mem automatically prevents duplicate imports using composite keys:

| Record Type | Detection Key |
|-------------|---------------|
| Sessions | `claude_session_id` |
| Summaries | `sdk_session_id` |
| Observations | `sdk_session_id` + `title` + `created_at_epoch` |
| Prompts | `claude_session_id` + `prompt_number` |

**Safe to reimport**: Running import multiple times on the same file has no adverse effects.

## Privacy and Security

**WARNING**: Export files contain **plain text** memory data. Before sharing:

1. Review export files for sensitive information:
   - API keys, tokens, passwords
   - Private file paths
   - Confidential business logic
   - Personal identifying information

2. Use `jq` to filter sensitive records:

   ```bash
   cat export.json | jq 'del(.observations[] | select(.content | contains("API_KEY")))' > filtered.json
   ```

3. Consider separate exports for public vs private knowledge

## Git Workflow Integration

### What to Commit

**COMMIT** to git:

- `*.json` - Session-exported memories (after privacy review)
- `README.md` - This documentation

**DO NOT COMMIT**:

- Any files with sensitive data (review before committing)

### Session Protocol Integration

**Session Start (Optional)**:

```bash
# Auto-import all memories (idempotent)
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1
```

Can be added to `.claude/hooks/SessionStart.ps1` for automatic execution.

**Session End (Required for memory-heavy sessions)**:

```bash
# Export session memories
npx tsx scripts/export-memories.ts "[topic]" .claude-mem/memories/YYYY-MM-DD-session-NNN-[topic].json
```

## Example Workflows

### Sharing Frustration Patterns (This Session)

```bash
# Export frustration pattern memories created in session 229
npx tsx scripts/export-memories.ts "frustration pattern" \
  .claude-mem/memories/2026-01-03-session-229-frustrations.json

# Commit to git
git add .claude-mem/memories/2026-01-03-session-229-frustrations.json
git commit -m "feat(memory): export frustration pattern learnings from session 229"
```

### Onboarding New Team Member

```bash
# New team member clones repo
git clone https://github.com/user/ai-agents.git
cd ai-agents

# Auto-import all memories (idempotent)
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1

# Verify import
npx tsx scripts/search-memories.ts "frustration pattern"
```

### Importing Shared Knowledge from Teammate

```bash
# Receive export file from teammate (via Slack, email, etc.)
# Save to memories/ directory
mv ~/Downloads/teammate-learnings.json .claude-mem/memories/

# Auto-import (idempotent, will import the new file)
pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1

# Or import manually
npx tsx scripts/import-memories.ts .claude-mem/memories/teammate-learnings.json
```

## Quality Guidelines

### What to Export

**DO export**:

- Session-specific learnings (frustration patterns, meta-patterns, timelines)
- Architecture decisions and rationale
- Debugging insights and root cause analyses
- Testing strategies and coverage philosophies
- Tool usage patterns and anti-patterns

**DO NOT export**:

- Temporary debugging observations
- Personal preferences not relevant to project
- Duplicate knowledge already in shared exports
- Sensitive information (see Privacy section)

### Export Naming Conventions

Follow consistent naming for discoverability:

- Session exports: `YYYY-MM-DD-session-NNN-topic.json`
- Thematic exports: `YYYY-MM-DD-theme-name.json`
- Onboarding sets: `onboarding-YYYY-MM-DD.json`

### Memory Hygiene

Before exporting:

1. **Review quality**: Are memories atomic? (<2000 chars, one concept)
2. **Check duplicates**: Does this knowledge already exist in exports?
3. **Verify relevance**: Will this help future sessions?
4. **Remove cruft**: Delete debugging observations before export

## Troubleshooting

### Import Fails with "Database not found"

Ensure Claude-Mem MCP server has been initialized:

```bash
# Check if database exists
ls ~/.claude-mem/

# If not, start Claude Code to initialize MCP servers
```

### Export Contains No Results

Check query syntax and memory creation timestamps:

```bash
# List recent observations
npx tsx scripts/search-memories.ts "" | head -20

# Try broader query
npx tsx scripts/export-memories.ts "" all.json
cat all.json | jq '.totalObservations'
```

### Duplicate Memories After Import

Not possible due to automatic duplicate detection. If seeing apparent duplicates:

1. Check `memory_id` - likely different IDs
2. Verify content is actually identical
3. May be intentional (e.g., cross-project patterns)

## References

- [Claude-Mem Export/Import Docs](https://docs.claude-mem.ai/usage/export-import)
- [SESSION-PROTOCOL.md](../../.agents/SESSION-PROTOCOL.md) - Session workflow integration
- [ADR-007: Memory-First Architecture](../../.agents/architecture/ADR-007-memory-first-architecture.md)
- Forgetful MCP: Similar capability for semantic memory system

## Changelog

### 2026-01-03

- Initial directory creation
- Export/import workflow documentation
- Git integration guidelines
- Privacy and security guidelines
