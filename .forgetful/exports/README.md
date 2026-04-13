# Forgetful Database Exports

JSON exports from the Forgetful SQLite database for version control and team sharing.

## Purpose

Share Forgetful memories across team members and installations while maintaining version control integration.

## Critical Limitations

**WARNING: ID-based sync is NOT suitable for bidirectional synchronization between divergent databases.**

See `scripts/forgetful/README.md` for detailed explanation and supported use cases.

**Safe Usage:**

- Backup/restore on same machine
- Fresh database initialization
- One-way sync (primary to secondary)

**Unsafe Usage:**

- Bidirectional sync between divergent databases
- Team collaboration with concurrent edits on different machines

## Directory Structure

```text
.forgetful/
└── exports/
    ├── README.md (this file)
    ├── 2026-01-13-session-905-architecture.json
    ├── 2026-01-13-session-906-patterns.json
    └── 2026-01-14-full-backup.json
```

All export files at root level (no subdirectories).

## Workflow

### Export (Session End)

```powershell
# Export by session number and topic
pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -SessionNumber 905 -Topic "architecture"

# Output: .forgetful/exports/2026-01-13-session-905-architecture.json

# Security review (MANDATORY)
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile .forgetful/exports/2026-01-13-session-905-architecture.json

# Commit if clean
git add .forgetful/exports/2026-01-13-session-905-architecture.json
git commit -m "docs(memory): export session 905 learnings - architecture decisions"
```

### Import (Session Start)

```powershell
# Import all shared memories (idempotent)
pwsh scripts/forgetful/Import-ForgetfulMemories.ps1

# Output: Imports all .json files from this directory
```

## Naming Convention

- **Session exports**: `YYYY-MM-DD-session-NNN-topic.json`
- **Thematic exports**: `YYYY-MM-DD-topic.json`
- **Full backups**: `YYYY-MM-DD-full-backup.json`

## Export Format

```json
{
  "export_metadata": {
    "export_timestamp": "2026-01-13T17:00:00Z",
    "database_path": "/home/user/.local/share/forgetful/forgetful.db",
    "schema_version": "abc123",
    "exported_tables": ["users", "memories", "projects", ...],
    "export_tool": "Export-ForgetfulMemories.ps1"
  },
  "data": {
    "users": [...],
    "memories": [...],
    "projects": [...],
    "entities": [...],
    "documents": [...],
    "code_artifacts": [...],
    "memory_links": [...],
    "memory_project_association": [...],
    "memory_code_artifact_association": [...],
    "memory_document_association": [...],
    "memory_entity_association": [...],
    "entity_project_association": [...],
    "entity_relationships": [...]
  }
}
```

## Security Review (MANDATORY)

**ALWAYS** run security review before committing exports to git.

**Command:**

```powershell
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile [file].json
```

**Detects:**

- API keys, tokens, passwords, secrets
- Private file paths and PII
- Database connection strings
- Private keys

Exit code 0 = safe to commit, 1 = sensitive data found (blocks commit)

## Idempotency

Import is idempotent. Safe to run multiple times.

**Default Behavior (Replace mode):**

- Uses `INSERT OR REPLACE` for upsert semantics
- New records inserted, existing records updated
- Primary keys determine uniqueness

**Merge Modes:**

| Mode | SQL Operation | Behavior |
|------|---------------|----------|
| `Replace` | `INSERT OR REPLACE` | Upsert (default) |
| `Skip` | `INSERT OR IGNORE` | Insert new only |
| `Fail` | `INSERT` | Abort on duplicate |

## Git Integration

### What to Commit

- ✅ Export JSON files (after security review passes)
- ✅ README.md files

### What NOT to Commit

- ❌ Exports failing security review
- ❌ Temporary/backup files (`.bak`, `.tmp`)

### .gitignore

```gitignore
# Temporary files
*.bak
*.tmp
*.swp

# DO commit .json exports (after security review)
```

## Team Collaboration

### Sharing Learnings

1. Export session memories at session end
2. Run security review
3. Commit to git
4. Teammates import at session start

### Onboarding

1. Export comprehensive project memories
2. New team member imports on setup
3. Instant access to project knowledge

### Disaster Recovery

1. Restore memories from git history
2. Import to rebuild Forgetful database
3. All historical context preserved

## Related Documentation

- `scripts/forgetful/README.md` - Script usage
- `scripts/Review-MemoryExportSecurity.ps1` - Security scanner
- `.agents/SESSION-PROTOCOL.md` - Session workflow integration
- ADR-007 - Memory-First Architecture

## Requirements

- PowerShell 7.5.4+ (cross-platform)
- SQLite3 command-line tool
- Forgetful MCP server installed

## Support

For issues or questions:

1. Check `scripts/forgetful/README.md` for troubleshooting
2. Verify SQLite3 is installed and available
3. Ensure Forgetful database is initialized
