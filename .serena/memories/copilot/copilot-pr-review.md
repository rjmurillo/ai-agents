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

## Metrics (PR #249)

Signal: 21% (↓ from 35%) | False positives: 64% (↑ from 10%)

**→ Prioritize cursor[bot] first. Increase verification.**

## Response Templates

| Situation | Template |
|-----------|----------|
| Accept | "Thanks @Copilot! Good catch." |
| Intentional | "@Copilot Intentional. Will update source docs." |
| Revert | "@Copilot Will update to match source." |

## Related

- [copilot-cli-model-configuration](copilot-cli-model-configuration.md)
- [copilot-directive-relocation](copilot-directive-relocation.md)
- [copilot-follow-up-pr](copilot-follow-up-pr.md)
- [copilot-platform-priority](copilot-platform-priority.md)
- [copilot-supported-models](copilot-supported-models.md)
