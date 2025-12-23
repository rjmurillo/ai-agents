# Copilot PR Review Patterns

## Documentation Consistency Checking

Copilot cross-references inlined content against source documentation and flags discrepancies.

**Characteristics**:
- Identifies when inlined content differs from source documentation
- Provides specific code suggestions for fixes
- Comments are VALID (not false positives) for consistency checking
- Multiple comments may be generated for same issue across files

## Sequence Consistency Checking

Copilot identifies when documented workflows/sequences are incomplete.

**Trigger**: Cross-references agent sequences against Phase documentation.

## Triage Classification

| Comment Type | Likely Path | Handling |
|--------------|-------------|----------|
| Missing table row/entry | Quick Fix | Accept suggestion |
| Content differs from source | Standard | Investigate intent |
| Missing sequence element | Quick Fix | Apply across all files |
| Sequence differs from Phase | Quick Fix | Verify Phase docs are truth |
| Typo/formatting | Quick Fix | Accept suggestion |

## False Positive Patterns

### Contradictory Comments

- Same PR may have contradictory comments (e.g., "needs read permission" then "write permission is too broad")
- Both cannot be valid; indicates contextual confusion
- **Action**: Ignore the contradictory pair

### PowerShell Escape Misunderstanding

- Copilot misunderstands backtick escapes (`` `a ``, `` `n ``)
- **Action**: Skip PowerShell escape false positives

### Duplicate Detection

- Copilot often echoes cursor[bot] findings later
- **Action**: Check cursor[bot] first, note as duplicate

## Actionability Metrics

| Metric | Historical | PR #249 | Trend |
|--------|------------|---------|-------|
| Signal Quality | ~35% | 21% | ↓ DECLINING |
| False Positives | ~10% | 64% | ↑ INCREASING |

**Recommendation**: Prioritize cursor[bot] comments first. Increase verification rigor.

## Response Templates

| Situation | Template |
|-----------|----------|
| Accept | "Thanks @Copilot! Good catch - I'll make this update." |
| Keep PR version | "@Copilot The change is intentional. I'll update source documentation." |
| Revert to source | "@Copilot Thanks for the consistency check. I'll update to match source." |

## Index

Parent: `skills-copilot-index`
