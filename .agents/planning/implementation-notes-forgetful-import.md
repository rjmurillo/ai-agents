# Forgetful Full-Backup Import Notes

## Scope

Issue #4949 reports that the committed January 19 full backup crashes the
Forgetful importer before later correction exports can run.

The importer now normalizes each table value before schema lookup or database
writes:

- The export root and `data` section must be objects.
- JSON `null` becomes an empty table.
- One JSON object becomes a one-row table.
- An array is accepted only when every row is an object.
- Other values fail with the input file and table in the diagnostic.

## Export Contracts

The current producer contract is defined at
`scripts/forgetful/export_forgetful_memories.py:97`:

```python
def export_table(db_path: str, table: str) -> list[dict[str, Any]]:
```

The historical producer at
`a333cb70c^:scripts/forgetful/Export-ForgetfulMemories.ps1` assigned parsed
JSON directly to every table:

```powershell
$ParsedData = $TableData | ConvertFrom-Json
$ExportData.data[$Table] = $ParsedData
```

That PowerShell conversion can collapse one-row arrays to an object and empty
arrays to null. Compatibility therefore applies to every table, not a
hard-coded table name.

The committed `.forgetful/exports/2026-01-19-full-backup.json` demonstrates
both legacy shapes. Its `users` value is an object with eight fields, and its
`memory_code_artifact_association` value is null.

## Validation

- Focused importer suites: 41 passed.
- Committed backup against a temporary database copy: 2,359 inserted, exit 0.
- Regression mutation: disabling object normalization fails the committed
  backup plus correction test.
- Ruff check and format check: passed.
- GPT-5.6 Sol adversarial review: approved.
- Independent security review: approved.

## Security Flagging

**Status**: Security-relevant input validation reviewed

**Triggered By**: Local JSON input processing and existing database file
operations

**PIV Required**: Completed

**Threat Model**:

- Attack surface: CLI-selected local JSON export files.
- Threat actor: a local user or process that can supply an export file.
- Impact: malformed rows could otherwise reach existing SQL generation or
  terminate a multi-file correction import.

The new validation rejects malformed table and row shapes before writes for
that table. It adds no path handling, shell invocation, or SQL construction.
The CWE-78 scanner examined both changed Python files and found zero
vulnerabilities. The security agent found no unmitigated CWE-20, CWE-22,
CWE-78, CWE-89, or CWE-400 risk in changed lines.

## Trade-offs

1. Validation is table-generic because the historical exporter applied one
   conversion path to every table.
2. Existing per-file error handling remains unchanged, so a malformed file
   does not prevent later input files from running.
3. Per-file transactions remain outside this fix. Earlier tables in one file
   may already be committed if a later table is malformed.
