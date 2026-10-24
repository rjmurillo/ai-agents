# Claude-Mem Shared Memories

This directory contains exportable memory snapshots from the Claude-Mem MCP server for sharing across team members, installations, and sessions.

## Purpose

Claude-Mem memories are local to each installation. Export enables:

1. **Team collaboration** - Share learnings across developers
2. **Cross-session persistence** - Version control memories alongside code
3. **Disaster recovery** - Keep memories reachable in git history

This repository no longer ships an import wrapper (owner decision D21 (2026-10-24), issue #5583). To load an export into a Claude-Mem installation, follow the upstream [Claude-Mem Export/Import Docs](https://docs.claude-mem.ai/usage/export-import).

## Directory Structure

```text
.claude-mem/memories/
├── AGENTS.md                                          # Agent guide for this directory
├── README.md                                          # This file
└── (topic-scoped exports, when committed)
```

Topic-scoped exports are stored in this single directory.

**Note**: Full-database `direct-backup-*.json` exports are generated locally and are not committed. Topic-scoped session exports may still be committed after the privacy review in the Privacy and Security section below.

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

**Note**: The three Python wrappers under `.claude-mem/scripts/` (`export_claude_mem_memories.py`, `export_claude_mem_full_backup.py`, `export_claude_mem_direct.py`) are the tracked entry points. The first two forward to the installed claude-mem plugin scripts at `~/.claude/plugins/marketplaces/thedotmack/scripts/`. `export_claude_mem_direct.py` reads the plugin's SQLite database directly.

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

- Full-database `direct-backup-*.json` exports (generated locally)
- Any files with sensitive data (review before committing)

### Session Protocol Integration

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

### "Database not found"

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

## References

- [Claude-Mem Export/Import Docs](https://docs.claude-mem.ai/usage/export-import)
- [Session Log Mechanics](../../.claude/rules/session-logs.md) - Session workflow integration
- [ADR-007: Memory-First Architecture](../../.agents/architecture/ADR-007-memory-first-architecture.md)
- Forgetful MCP: Similar capability for semantic memory system

## Changelog

### 2026-10-24

- Retired the manual import procedure and removed the committed `direct-backup-2026-01-03-1434-ai-agents.json` export (issue #5583, owner decision D21 (2026-10-24))
- Fixed the Directory Structure block to list the files that exist

### 2026-01-03

- Initial directory creation
- Export/import workflow documentation
- Git integration guidelines
- Privacy and security guidelines
