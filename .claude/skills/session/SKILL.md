# Session Skills

Skills for session management and protocol compliance.

## Test Investigation Eligibility

Check if staged files qualify for investigation-only QA skip.

### Usage

```powershell
pwsh .claude/skills/session/scripts/Test-InvestigationEligibility.ps1
```

### Output

Returns JSON with:

- `Eligible`: boolean - true if all staged files are in allowlist
- `StagedFiles`: array of all staged file paths
- `Violations`: array of files not in allowlist (empty if eligible)
- `AllowedPaths`: reference list of allowed path prefixes

### Example

```json
{
  "Eligible": true,
  "StagedFiles": [".agents/sessions/2025-01-01-session-01.md"],
  "Violations": [],
  "AllowedPaths": [
    ".agents/sessions/",
    ".agents/analysis/",
    ".agents/retrospective/",
    ".serena/memories/",
    ".agents/security/"
  ]
}
```

### When to Use

Before committing with `SKIPPED: investigation-only` QA exemption:

1. Stage your files with `git add`
2. Run this skill to verify eligibility
3. If `Eligible: true`, safe to use investigation-only skip
4. If `Eligible: false`, check `Violations` for non-allowed files

### Related

- ADR-034: Investigation Session QA Exemption
- Issue #662: Create QA skip eligibility check skill
- Validate-Session.ps1: Uses same allowlist for validation
