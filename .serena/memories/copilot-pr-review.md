## Triage

| Comment Type | Action |
|--------------|--------|
| Missing table row | Accept |
| Content differs from source | Investigate |
| Missing sequence element | Apply across files |
| Typo/formatting | Accept |

## False Positives

| Pattern | Action |
|---------|--------|
| Contradictory comments (read vs write permission) | Ignore pair |
| PowerShell escapes (`` `a ``, `` `n ``) | Skip |
| Duplicates cursor[bot] | Note duplicate |

## Metrics

| PR | Signal | False Positives | Notes |
|----|--------|-----------------|-------|
| #249 | 21% | 64% | High noise, cursor[bot] duplicates |
| #308 | 62% | 38% | Table-only format FPs (4), phrasing FPs (2) |

**Trend**: Signal improved 41 points. New ADR-017 table-only format not yet learned by Copilot.

**→ Document table-only format in coderabbit config to reduce FPs.**

## Response Templates

| Situation | Template |
|-----------|----------|
| Accept | "Thanks @Copilot! Good catch." |
| Intentional | "@Copilot Intentional. Will update source docs." |
| Revert | "@Copilot Will update to match source." |
