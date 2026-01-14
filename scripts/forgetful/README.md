# Forgetful Database Export/Import Scripts

PowerShell scripts for exporting and importing the Forgetful SQLite database to/from JSON format.

## Purpose

Enable memory sharing across team members and installations while maintaining version control integration.

## Scripts

### Export-ForgetfulMemories.ps1

Export Forgetful database to JSON format.

**Usage:**

```powershell
# Export with session number and topic
pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -SessionNumber 905 -Topic "architecture"

# Export to custom file
pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -OutputFile .forgetful/exports/backup.json

# Export specific tables only
pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -Topic "memories-only" -IncludeTables "memories"
```

**Parameters:**

- `-OutputFile`: Path to output JSON file (default: `.forgetful/exports/YYYY-MM-DD-session-NNN-topic.json`)
- `-SessionNumber`: Session number for default filename
- `-Topic`: Topic for default filename
- `-DatabasePath`: Path to Forgetful database (default: `~/.local/share/forgetful/forgetful.db`)
- `-IncludeTables`: Comma-separated table list or 'all' (default: 'all')

**Output:**

```text
.forgetful/exports/2026-01-13-session-905-architecture.json
```

**Security Review:**

Export automatically runs security review script. Must pass before committing to git.

### Import-ForgetfulMemories.ps1

Import Forgetful database from JSON format.

**Usage:**

```powershell
# Import all files from exports directory
pwsh scripts/forgetful/Import-ForgetfulMemories.ps1

# Import specific files
pwsh scripts/forgetful/Import-ForgetfulMemories.ps1 -InputFiles @('.forgetful/exports/backup.json')

# Skip confirmation prompt
pwsh scripts/forgetful/Import-ForgetfulMemories.ps1 -Force
```

**Parameters:**

- `-InputFiles`: Array of JSON file paths (default: all `.json` files in `.forgetful/exports/`)
- `-DatabasePath`: Path to Forgetful database (default: `~/.local/share/forgetful/forgetful.db`)
- `-Force`: Skip confirmation prompt

**Idempotency:**

Safe to run multiple times. Existing records with matching primary keys are automatically skipped using `INSERT OR IGNORE`.

## Workflow

### Session Start

```powershell
# Import all shared memories (idempotent)
pwsh scripts/forgetful/Import-ForgetfulMemories.ps1
```

### Session End

```powershell
# Export by session number and topic
pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -SessionNumber 905 -Topic "patterns"

# Security review (REQUIRED)
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile .forgetful/exports/2026-01-13-session-905-patterns.json

# Commit if clean
git add .forgetful/exports/2026-01-13-session-905-patterns.json
git commit -m "docs(memory): export session 905 learnings - agent patterns"
```

## Naming Conventions

- Session exports: `YYYY-MM-DD-session-NNN-topic.json`
- Thematic exports: `YYYY-MM-DD-topic.json`
- All files directly in `.forgetful/exports/` (no subdirectories)

## Database Structure

Exported tables:

| Table | Description |
|-------|-------------|
| `users` | User accounts |
| `memories` | Atomic knowledge entries |
| `projects` | Project containers |
| `entities` | Real-world entities (people, orgs, devices) |
| `documents` | Long-form content |
| `code_artifacts` | Reusable code snippets |
| `memory_links` | Bidirectional memory relationships |
| `memory_project_association` | Memory-to-project links |
| `memory_code_artifact_association` | Memory-to-code links |
| `memory_document_association` | Memory-to-document links |
| `memory_entity_association` | Memory-to-entity links |
| `entity_project_association` | Entity-to-project links |
| `entity_relationships` | Entity relationships |

## Security Review

**MANDATORY** before committing exports to git.

**Script:**

```powershell
pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile [file].json
```

**Scans for:**

- API Keys/Tokens
- Passwords/Secrets
- Private Keys
- File Paths
- Database Credentials
- Email/PII

Exit code 0 = clean, 1 = sensitive data found (blocks commit)

## Requirements

- PowerShell 7.0+ (cross-platform)
- SQLite3 command-line tool
- Forgetful MCP server installed and database initialized

**Install SQLite3:**

- Ubuntu/Debian: `sudo apt-get install sqlite3`
- macOS: `brew install sqlite3`
- Windows: Download from [sqlite.org](https://www.sqlite.org/download.html)

## Integration

### Session Protocol

See `.agents/SESSION-PROTOCOL.md` for session start/end integration:

- **Phase 2.1 (Session Start)**: Import shared memories
- **Phase 0.5 (Session End)**: Export session memories

### Team Collaboration

1. **Sharing learnings**: Export session memories, commit to git, teammates import
2. **Onboarding**: Export project memories, new members import on setup
3. **Cross-session context**: Export after significant sessions, import at session start
4. **Disaster recovery**: Restore memories from git history

## Related

- `.forgetful/exports/README.md` - Workflow documentation
- `.claude-mem/scripts/` - Claude-Mem export/import (similar pattern)
- `scripts/Review-MemoryExportSecurity.ps1` - Security scanner
- ADR-005 - PowerShell-Only Scripting
- ADR-007 - Memory-First Architecture

## Troubleshooting

### Database Not Found

```text
Forgetful database not found at: ~/.local/share/forgetful/forgetful.db
```

**Solution:**

1. Verify Forgetful MCP server is installed
2. Create at least one memory via Forgetful to initialize database
3. Check if database exists at alternate location

### SQLite3 Not Found

```text
sqlite3 is not installed or not in PATH
```

**Solution:**

Install sqlite3 using package manager (see Requirements section).

### Export Security Review Failed

```text
Security review FAILED. Sensitive data detected in export.
```

**Solution:**

1. Review and redact sensitive data in export file
2. Re-run security review script
3. Only commit after review passes

### Import Failures

```text
Import completed with failures: N files failed
```

**Solution:**

1. Verify JSON file syntax is valid
2. Check export was created with `Export-ForgetfulMemories.ps1`
3. Ensure database schema version matches export
4. Check foreign key constraints are satisfied
