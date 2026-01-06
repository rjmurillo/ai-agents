# Session Protocol Validator Bug: Pipe Character Parsing

**Date**: 2026-01-05
**Discovered In**: Session 318 (PR #799 creation)
**Severity**: HIGH - Blocks session validation

## Problem

The `Validate-Session.ps1` script cannot parse the canonical Session End checklist from `SESSION-PROTOCOL.md` because it contains pipe characters `|` inside the security review grep command.

## Root Cause

`Parse-ChecklistTable` function splits markdown table rows on `|` characters (line 115):

```powershell
$parts = ($line.Trim() -replace '^\|','' -replace '\|$','').Split('|') | ForEach-Object { $_.Trim() }
```

The canonical security review row contains:
```
| MUST | Security review export (if exported): `grep -iE "api[_-]?key|password|token|secret|credential|private[_-]?key" [file].json` | [ ] | Scan result: "Clean" or "Redacted" |
```

The grep command has 4 pipe characters (`password|token|secret|credential|private`), which cause the parser to split the row into 9 parts instead of 4.

## Impact

- Session validation fails even when checklist is correctly filled out
- Blocks completion of sessions that properly follow SESSION-PROTOCOL.md template
- Creates false negative validation failures

## Workaround

None currently. Sessions cannot pass validation if they use the canonical security review row.

## Fix Recommendation

Replace `.Split('|')` with a regex that respects backtick-quoted sections or markdown code spans. Example:

```powershell
# Use regex to split on pipes that aren't inside backticks
# This is complex - may need to tokenize the line properly
```

Or simpler: escape pipes inside code spans in the canonical template:

```
`grep -iE "api[_-]?key\|password\|token...`
```

## Related

- PR #799: Session protocol validator enhancements
- Session 318: PR creation session
- File: scripts/Validate-Session.ps1 line 115
- Canonical template: .agents/SESSION-PROTOCOL.md lines 472-485, 573-586
