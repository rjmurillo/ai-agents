# Template Extraction Guide

How to extract the session log template from SESSION-PROTOCOL.md.

---

## Template Location

**File**: `.agents/SESSION-PROTOCOL.md`
**Lines**: 494-612
**Section**: `## Session Log Template`

---

## Extraction Steps

### 1. Read the Source File

```powershell
$content = Get-Content -Path ".agents/SESSION-PROTOCOL.md" -Raw
```

### 2. Extract Template Section

The template starts at `## Session Log Template` and ends before the next `---` section divider.

```powershell
# Find template section
$pattern = '(?s)## Session Log Template.*?```markdown\r?\n(.*?)```'
if ($content -match $pattern) {
    $template = $Matches[1]
}
```

### 3. Alternative: Line-Based Extraction

If regex is unreliable, use line-based extraction:

```powershell
$lines = Get-Content -Path ".agents/SESSION-PROTOCOL.md"
$template = $lines[498..610] -join "`n"
```

---

## Critical Formatting Elements

These elements MUST be preserved exactly:

### Header Levels

| Section | Level | Format |
|---------|-------|--------|
| Title | H1 | `# Session NN - YYYY-MM-DD` |
| Session Info | H2 | `## Session Info` |
| Protocol Compliance | H2 | `## Protocol Compliance` |
| Session Start | H3 | `### Session Start (COMPLETE ALL before work)` |
| Session End | H3 | `### Session End (COMPLETE ALL before closing)` |
| Work Log | H2 | `## Work Log` |

### Table Structure

Tables use pipe separators with exact column alignment:

```markdown
| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | [Step description] | [ ] | [Evidence placeholder] |
```

### Checkbox Format

Unchecked boxes use `[ ]` with a space inside:

```markdown
| MUST | Step | [ ] | Evidence |
```

### Comment Blocks

HTML comments must be preserved:

```markdown
<!-- Investigation sessions may skip QA with evidence "SKIPPED: investigation-only"
     when only staging: .agents/sessions/, .agents/analysis/, .agents/retrospective/,
     .serena/memories/, .agents/security/
     See ADR-034 for details. -->
```

---

## The Critical Text

**MOST IMPORTANT**: The Session End header MUST include `(COMPLETE ALL before closing)`:

```markdown
### Session End (COMPLETE ALL before closing)
```

**NOT**:

```markdown
## Session End
```

This is the most common validation failure. The regex in `Validate-SessionJson.ps1` checks for:

```regex
(?i)Session\s+End.*COMPLETE\s+ALL|End.*before.*closing
```

---

## Verification

After extraction, verify the template contains:

```powershell
$checks = @(
    '## Session Info',
    '## Protocol Compliance',
    '### Session Start (COMPLETE ALL before work)',
    '### Session End (COMPLETE ALL before closing)',
    '## Work Log',
    '## Notes for Next Session'
)

foreach ($check in $checks) {
    if ($template -notmatch [regex]::Escape($check)) {
        Write-Error "Missing: $check"
    }
}
```

---

## Template Cache

For performance, the template can be cached during a session, but MUST be re-read if:

- SESSION-PROTOCOL.md has been modified
- Starting a new session after file system changes
- Validation fails (re-read to check for template updates)
