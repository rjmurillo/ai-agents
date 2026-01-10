# Claude-Mem Export Enhancements - Technical Specification

**Version**: 1.0.0
**Created**: 2026-01-04
**Status**: Implemented
**PR**: #753

---

## Overview

Comprehensive export functionality for Claude-Mem (sqlite3-based semantic memory system) with security validation, duplicate detection fixes, and full data fidelity.

### Problem Statement

1. **Incomplete exports**: FTS-based export only captures ~2% of data (search index, not full content)
2. **Missing fields**: `sdk_session_id` not exported, breaking duplicate detection on re-import
3. **NULL titles**: Some memories have NULL titles which cause import failures
4. **No backup workflow**: No automated full backup/restore capability
5. **No security validation**: Exports could contain sensitive data without review

### Solution

Direct SQLite export with 100% data fidelity, automated security review, and comprehensive backup workflow.

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority | Implementation |
|----|-------------|----------|----------------|
| FR-001 | Export all memory fields (title, content, context, tags, importance, timestamps, sdk_session_id) | MUST | Export-ClaudeMemDirect.ps1 |
| FR-002 | Fix NULL titles (replace with empty string) | MUST | Export-ClaudeMemDirect.ps1 |
| FR-003 | Include sdk_session_id for duplicate detection | MUST | Export-ClaudeMemDirect.ps1 |
| FR-004 | Automated security review (BLOCKING) | MUST | Export-ClaudeMemFullBackup.ps1 |
| FR-005 | JSON output format for portability | MUST | Export-ClaudeMemDirect.ps1 |
| FR-006 | Full backup workflow with validation | SHOULD | Export-ClaudeMemFullBackup.ps1 |
| FR-007 | Export memories only (not documents/code artifacts) | MUST | Export-ClaudeMemMemories.ps1 |

### Non-Functional Requirements

| ID | Requirement | Priority | Implementation |
|----|-------------|----------|----------------|
| NFR-001 | PowerShell-only (ADR-005 compliance) | MUST | All scripts .ps1 |
| NFR-002 | Cross-platform (Windows/Linux/macOS) | MUST | sqlite3 CLI tool |
| NFR-003 | Pester test coverage | SHOULD | Export-ClaudeMemFullBackup.Tests.ps1 |
| NFR-004 | Idempotent (safe to run multiple times) | SHOULD | All scripts |
| NFR-005 | Error handling for missing database | MUST | Parameter validation |

---

## Architecture

### Component Overview

```text
┌─────────────────────────────────────────────────┐
│ Export-ClaudeMemDirect.ps1                     │
│ • Direct SQLite export                          │
│ • 100% data fidelity                            │
│ • NULL title fixes                              │
│ • sdk_session_id included                       │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│ Export-ClaudeMemFullBackup.ps1                 │
│ • Orchestration layer                           │
│ • Security review (BLOCKING)                    │
│ • Backup file management                        │
│ • Validation                                    │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│ Export-ClaudeMemMemories.ps1                   │
│ • Legacy: FTS-based export (~2% data)           │
│ • DEPRECATED: Use Direct export                 │
└─────────────────────────────────────────────────┘
```

### Data Flow

```text
Claude-Mem SQLite DB
        │
        ▼
    sqlite3 CLI
        │
        ├─→ SELECT id, title, content, ...
        │   FROM memories
        │   WHERE is_obsolete = 0
        │
        ▼
    JSON output
        │
        ├─→ Fix NULL titles (→ empty string)
        │
        ├─→ Include sdk_session_id
        │
        ▼
    Security Review
        │
        ├─→ Scan for secrets (API keys, tokens, passwords)
        │
        ├─→ BLOCKING if secrets found
        │
        ▼
    Backup File
        │
        └─→ .claude-mem/backups/direct-backup-YYYY-MM-DD-HHMM-{project}.json
```

---

## Implementation

### Export-ClaudeMemDirect.ps1

**Purpose**: Direct SQLite export with 100% data fidelity

**Parameters**:
```powershell
param(
    [Parameter(Mandatory)]
    [string]$DatabasePath,

    [Parameter()]
    [string]$OutputPath
)
```

**SQL Query**:
```sql
SELECT
    id,
    COALESCE(title, '') as title,  -- Fix NULL titles
    content,
    context,
    keywords,
    importance,
    tags,
    created_at,
    updated_at,
    user_id,
    project_id,
    sdk_session_id,  -- CRITICAL: Required for duplicate detection
    is_obsolete
FROM memories
WHERE is_obsolete = 0
ORDER BY created_at DESC
```

**Output Format**:
```json
[
  {
    "id": 1,
    "title": "Memory title",
    "content": "Memory content...",
    "context": "Why this matters",
    "keywords": "keyword1,keyword2",
    "importance": 8,
    "tags": "tag1,tag2",
    "created_at": "2026-01-03T14:30:00Z",
    "updated_at": "2026-01-03T14:30:00Z",
    "user_id": 1,
    "project_id": 1,
    "sdk_session_id": "session-abc123",
    "is_obsolete": 0
  }
]
```

**Error Handling**:
- Validate DatabasePath exists
- Check sqlite3 is installed
- Graceful failure if query fails
- Return exit code 1 on errors

---

### Export-ClaudeMemFullBackup.ps1

**Purpose**: Automated full backup with security review

**Parameters**:
```powershell
param(
    [Parameter()]
    [string]$ProjectName = "ai-agents",

    [Parameter()]
    [switch]$SkipSecurityReview
)
```

**Workflow**:

1. **Locate Database**:
   - Default: `.claude-mem/memories.db`
   - Validate exists

2. **Export**:
   - Call `Export-ClaudeMemDirect.ps1`
   - Output to `.claude-mem/backups/direct-backup-{timestamp}-{project}.json`

3. **Security Review** (BLOCKING):
   - Scan export for secrets using patterns:
     - API keys: `api[_-]?key`
     - Tokens: `token`
     - Passwords: `password`
     - GitHub PATs: `ghp_`, `gho_`
   - If secrets found:
     - Write error
     - Exit 1 (BLOCKING)
   - If `-SkipSecurityReview`: warn but continue

4. **Validation**:
   - Verify JSON parses
   - Verify file size > 0
   - Verify memory count > 0

5. **Output**:
   - File path
   - Memory count
   - File size
   - Security review status

---

### Export-ClaudeMemMemories.ps1

**Status**: DEPRECATED

**Reason**: FTS-based export only captures ~2% of data (search index, not full memories)

**Migration**: Use `Export-ClaudeMemDirect.ps1` instead

---

## Testing

### Pester Tests (Export-ClaudeMemFullBackup.Tests.ps1)

**Test Coverage**:

1. **Happy Path**:
   - Export succeeds with valid database
   - Output file created
   - JSON is valid
   - Memory count > 0

2. **Error Cases**:
   - Missing database → error
   - Invalid database → error
   - sqlite3 not installed → error

3. **Security Review**:
   - Secrets detected → blocked
   - No secrets → passes
   - `-SkipSecurityReview` → warns but continues

4. **Data Integrity**:
   - NULL titles fixed
   - sdk_session_id included
   - All expected fields present

---

## Security

### Security Review Process

**Automated Scan**:
```powershell
# Pattern matching for common secrets
$secretPatterns = @(
    'api[_-]?key',
    'token',
    'password',
    'ghp_',    # GitHub PAT
    'gho_',    # GitHub OAuth
    'sk-'      # OpenAI API key
)

foreach ($pattern in $secretPatterns) {
    if ($exportContent -match $pattern) {
        Write-Error "SECURITY: Export contains potential secret matching pattern: $pattern"
        exit 1
    }
}
```

**Manual Review**:
- Review `.claude-mem/backups/` before committing
- Never commit backup files to git
- Use `.gitignore` to block `*.json` in backups directory

---

## Usage

### Full Backup (Recommended)

```powershell
# Automated backup with security review
& .claude-mem/scripts/Export-ClaudeMemFullBackup.ps1
```

### Direct Export (Advanced)

```powershell
# Manual export with custom path
& .claude-mem/scripts/Export-ClaudeMemDirect.ps1 `
    -DatabasePath ".claude-mem/memories.db" `
    -OutputPath "my-backup.json"
```

---

## Validation Criteria

### Acceptance Tests

| Test | Expected Result |
|------|----------------|
| Export all memories | Count matches database `SELECT COUNT(*) FROM memories WHERE is_obsolete = 0` |
| NULL titles fixed | Zero NULL titles in export JSON |
| sdk_session_id included | All memories have sdk_session_id field |
| Security review blocks secrets | Exit 1 if patterns matched |
| JSON valid | `ConvertFrom-Json` succeeds |
| Re-import succeeds | Import to clean database, no duplicates |

---

## Migration Notes

### From FTS Export to Direct Export

**Old** (Export-ClaudeMemMemories.ps1):
- ~2% data capture (FTS index only)
- Missing sdk_session_id
- NULL titles cause import failures

**New** (Export-ClaudeMemDirect.ps1):
- 100% data capture
- Includes sdk_session_id
- NULL titles fixed

**Action Required**:
- Re-export existing backups using Direct export
- Update documentation to recommend Direct export
- Deprecate FTS export script

---

## Related

- **ADR-005**: PowerShell-Only Scripting
- **Issue #752**: Memory System Foundation
- **PR #753**: Claude-Mem Export Enhancements

---

## Changelog

### v1.0.0 (2026-01-04)

- Initial implementation
- Direct SQLite export
- Automated security review
- Full backup workflow
- Pester test coverage
- NULL title fix
- sdk_session_id inclusion
