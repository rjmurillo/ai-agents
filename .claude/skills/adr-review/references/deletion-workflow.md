# ADR Deletion Workflow

When an ADR file is deleted, this skill triggers a special workflow.

## Phase D1: Deletion Detection

```powershell
# Script detects deleted ADR files
& .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1

# Output includes:
# - Deleted file path
# - Last known status (proposed/accepted/deprecated/superseded)
# - Dependent ADRs that reference this ADR
```

## Phase D2: Impact Assessment

Invoke analyst to assess deletion impact:

```python
Task(subagent_type="analyst", prompt="""
ADR Deletion Impact Assessment

## Deleted ADR
Path: {deleted_adr_path}
Title: {adr_title}
Status: {last_known_status}

## Research Tasks
1. Find all references to this ADR in codebase
2. Check for dependent ADRs that cite this ADR
3. Identify any implementation code that references this decision
4. Check session logs for recent related work

## Output Format

### References Found
| Location | Type | Impact |
|----------|------|--------|
| [path] | [code/adr/doc] | [high/medium/low] |

### Recommendation
- **Archive**: Keep copy in `.agents/architecture/archive/`
- **Delete**: No dependencies, safe to remove
- **Block**: Active dependencies require resolution first
""")
```

## Phase D3: Archival Decision

Based on impact assessment:

| Status | Dependencies | Action |
|--------|--------------|--------|
| proposed | None | Delete (no archival needed) |
| proposed | Exists | Block deletion, resolve deps |
| accepted | None | Archive then delete |
| accepted | Exists | Block deletion, update deps first |
| deprecated | Any | Archive then delete |
| superseded | Any | Verify successor ADR, then delete |

## Archival Format

If archiving is required:

```markdown
# Archived: ADR-NNN-title

**Archived**: YYYY-MM-DD
**Reason**: [User deleted | Superseded by ADR-XXX | Deprecated]
**Original Status**: [accepted | proposed | deprecated]

---

[Original ADR content preserved below]
```

Save to: `.agents/architecture/archive/ADR-NNN-title.md`

## Phase D4: Cleanup

1. Update dependent ADRs to remove/update references
2. Update any CLAUDE.md files that referenced the ADR
3. Log deletion in session log
4. Return summary to orchestrator

```markdown
## ADR Deletion Complete

**ADR**: [Path]
**Action**: [Archived | Deleted | Blocked]

### Changes Made
- [List of files updated]

### Archive Location (if archived)
- [Path to archived file]

### Blocked (if applicable)
- **Reason**: [Why deletion was blocked]
- **Required Actions**: [What must happen first]
```
