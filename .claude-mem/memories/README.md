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
├── direct-backup-2026-01-03-1434-ai-agents.json     # Full backup (security reviewed)
└── ...
```

All memory exports are stored in this single directory. Auto-import on session start handles idempotent loading.

**Note**: Large backup files (like `direct-backup-*.json`) are intentionally committed after security review to serve as test data and onboarding references. All committed exports have passed automated secret scanning.

## Export Workflow (Session End)

When ending a session, export memories created during that session:

```bash
# Export by topic/session (writes .claude-mem/memories/<today>-session-229-<topic>.json)
uv run python .claude-mem/scripts/export_claude_mem_memories.py "session 229" --session-number 229 --topic testing

# Export to an explicit file inside .claude-mem/memories/
uv run python .claude-mem/scripts/export_claude_mem_memories.py "session 229" --output-file .claude-mem/memories/2026-01-03-session-229.json

# Export project-specific memories (complete backup straight from the SQLite database)
uv run python .claude-mem/scripts/export_claude_mem_direct.py --project ai-agents
```

**Naming Convention**: `YYYY-MM-DD-session-NNN-topic.json`

**Note**: The four Python wrappers under `.claude-mem/scripts/` (`export_claude_mem_memories.py`, `export_claude_mem_full_backup.py`, `export_claude_mem_direct.py`, `import_claude_mem_memories.py`) are the tracked entry points. The export and import wrappers forward to the installed claude-mem plugin scripts at `~/.claude/plugins/marketplaces/thedotmack/scripts/`.

## Import Workflow (Session Start or Onboarding)

### Automatic Import (Session Start)

The auto-import script runs idempotently on session start:

```bash
# Automatically imports all .json files from .claude-mem/memories/
uv run python .claude-mem/scripts/import_claude_mem_memories.py
```

**Session Protocol Integration**: Can be added to a SessionStart hook for automatic execution.

### Manual Import

Import new memories from teammates by saving the file under `.claude-mem/memories/` and running the importer, which loads every file in that directory:

```bash
uv run python .claude-mem/scripts/import_claude_mem_memories.py
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
uv run python .claude-mem/scripts/import_claude_mem_memories.py
```

Can be added to a SessionStart hook for automatic execution.

**Session End (Required for memory-heavy sessions)**:

```bash
# Export session memories
uv run python .claude-mem/scripts/export_claude_mem_memories.py "[topic]" --session-number NNN --topic "[topic]"
```

## Example Workflows

### Sharing Frustration Patterns (This Session)

```bash
# Export frustration pattern memories created in session 229
uv run python .claude-mem/scripts/export_claude_mem_memories.py "frustration pattern" \
  --output-file .claude-mem/memories/2026-01-03-session-229-frustrations.json

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
uv run python .claude-mem/scripts/import_claude_mem_memories.py

# Verify import: search "frustration pattern" with the claude-mem MCP search tool
```

### Importing Shared Knowledge from Teammate

```bash
# Receive export file from teammate (via Slack, email, etc.)
# Save to memories/ directory
mv ~/Downloads/teammate-learnings.json .claude-mem/memories/

# Auto-import (idempotent, will import the new file)
uv run python .claude-mem/scripts/import_claude_mem_memories.py
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
# Try a broader query
uv run python .claude-mem/scripts/export_claude_mem_memories.py "" --output-file .claude-mem/memories/all.json
jq '.totalObservations' .claude-mem/memories/all.json
```

Delete `all.json` afterward; it is a scratch export, not a shareable snapshot.

### Duplicate Memories After Import

Not possible due to automatic duplicate detection. If seeing apparent duplicates:

1. Check `memory_id` - likely different IDs
2. Verify content is actually identical
3. May be intentional (e.g., cross-project patterns)

## References

- [Claude-Mem Export/Import Docs](https://docs.claude-mem.ai/usage/export-import)
- [Session Log Mechanics](../../.claude/rules/session-logs.md) - Session workflow integration
- [ADR-007: Memory-First Architecture](../../.agents/architecture/ADR-007-memory-first-architecture.md)
- Forgetful MCP: Similar capability for semantic memory system

## Changelog

### 2026-01-03

- Initial directory creation
- Export/import workflow documentation
- Git integration guidelines
- Privacy and security guidelines
