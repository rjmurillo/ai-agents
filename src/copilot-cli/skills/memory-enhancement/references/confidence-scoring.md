# Confidence Scoring Guide

Understanding how memory confidence scores are calculated, interpreted, and maintained.

## Table of Contents

1. [Formula](#formula)
2. [Interpretation](#interpretation)
3. [When to Update](#when-to-update)
4. [Historical Tracking](#historical-tracking)
5. [Best Practices](#best-practices)

## Formula

Confidence is calculated as the ratio of valid citations to total citations:

```text
confidence = valid_citations / total_citations
```

**Where:**

- `valid_citations` = Number of citations where file exists, line is in bounds, and snippet matches
- `total_citations` = Total number of citations in memory frontmatter

**Special Cases:**

| Scenario | Confidence | Reasoning |
|----------|------------|-----------|
| No citations | 0.5 (default) | Neutral confidence (no verification data) |
| All citations valid | 1.0 | Maximum confidence |
| All citations invalid | 0.0 | Minimum confidence |

**Example Calculations:**

```text
# Memory with 3 citations: 2 valid, 1 stale
confidence = 2 / 3 = 0.6667 (66.7%)

# Memory with 5 citations: all valid
confidence = 5 / 5 = 1.0 (100%)

# Memory with 4 citations: all stale
confidence = 0 / 4 = 0.0 (0%)

# Memory with no citations
confidence = 0.5 (default)
```

## Interpretation

### Confidence Ranges

| Score Range | Label | Interpretation | Recommended Action |
|-------------|-------|----------------|-------------------|
| **0.9 - 1.0** | High Confidence | All or nearly all citations valid | Trust memory, use in decisions |
| **0.7 - 0.9** | Medium Confidence | Most citations valid, some stale | Review stale citations, consider updating |
| **0.5 - 0.7** | Low Confidence | Many stale citations | Update memory or mark obsolete |
| **0.0 - 0.5** | Very Low Confidence | Most citations invalid | Memory likely outdated, needs review |
| **0.5** | No Data | No citations to verify | Add citations to improve confidence |

### What Confidence Tells You

**High Confidence (0.9-1.0):**

- Citations point to valid code locations
- Code references are up-to-date
- Memory reflects current codebase state
- Safe to rely on this memory for decisions

**Medium Confidence (0.7-0.9):**

- Majority of citations are valid
- Some code has moved or changed
- Memory mostly accurate but needs attention
- Review before using in critical decisions

**Low Confidence (0.5-0.7):**

- Half or more citations are stale
- Significant code changes since memory created
- Memory may contain outdated information
- Update memory or mark obsolete

**Very Low Confidence (0.0-0.5):**

- Most or all citations are invalid
- Codebase has diverged significantly
- Memory likely no longer relevant
- Strong candidate for deletion or complete rewrite

**No Data (0.5 default):**

- Memory has no citations to verify
- Cannot assess accuracy programmatically
- Neutral confidence (neither trusted nor distrusted)
- Consider adding citations to improve trackability

## When to Update

### Automatic Updates

Confidence is automatically recalculated when:

1. **Adding citations**: `python -m memory_enhancement add-citation`
2. **Batch verification**: `python -m memory_enhancement verify-all`
3. **Explicit update**: `python -m memory_enhancement update-confidence`

### Manual Updates

Run explicit updates after:

1. **Major refactoring**: Code structure changes significantly
2. **File moves/renames**: Citations may point to old paths
3. **Code deletion**: Referenced code removed from codebase
4. **Periodic review**: Weekly/monthly health checks

**Example Workflow:**

```bash
# After refactoring src/ directory
python -m memory_enhancement verify-all

# Review stale memories
python -m memory_enhancement health

# Update specific memories
python -m memory_enhancement update-confidence memory-001
python -m memory_enhancement update-confidence memory-002
```

### CI Integration

Automate confidence updates in pull requests:

```yaml
# .github/workflows/memory-validation.yml
- name: Update Confidence Scores
  run: python -m memory_enhancement verify-all --json
  continue-on-error: true

- name: Report Stale Memories
  if: failure()
  run: python -m memory_enhancement health --format markdown > memory-health.md
```

This ensures confidence scores are updated whenever code changes affect citations.

## Historical Tracking

### Current Implementation

The current version tracks:

- **Latest confidence score** - Stored in YAML frontmatter `confidence` field
- **Last verification timestamp** - Stored in `last_verified` field
- **Per-citation verification** - Each citation tracks its own `verified` timestamp

**Example Frontmatter:**

```yaml
---
subject: Input Validation Best Practices
tags: [security, validation]
confidence: 0.67
last_verified: 2026-01-24T15:30:00
citations:
  - path: src/api/validate.py
    line: 42
    snippet: "def validate_input"
    verified: 2026-01-24T15:30:00
    valid: true
  - path: src/api/sanitize.py
    line: 20
    snippet: "sanitize"
    verified: 2026-01-24T15:30:00
    valid: true
  - path: src/old/validator.py
    line: 10
    verified: 2026-01-24T15:30:00
    valid: false
    mismatch_reason: "File not found: src/old/validator.py"
---

# Content here...
```

### Future: Historical Tracking

Planned enhancement to track confidence over time:

```yaml
confidence_history:
  - timestamp: 2026-01-20T10:00:00
    score: 1.0
    valid_count: 3
    total_count: 3
  - timestamp: 2026-01-22T14:00:00
    score: 0.67
    valid_count: 2
    total_count: 3
  - timestamp: 2026-01-24T15:30:00
    score: 0.67
    valid_count: 2
    total_count: 3
```

This would enable:

- Trending analysis (is confidence improving or degrading?)
- Decay detection (memories becoming stale over time)
- Maintenance prioritization (focus on memories with declining confidence)

## Best Practices

### 1. Add Citations Early

Don't wait for confidence to drop - add citations when creating memories:

```bash
# When documenting a bug fix
python -m memory_enhancement add-citation bug-fix-memory \
  --file src/api.py \
  --line 42 \
  --snippet "fixed off-by-one error"
```

### 2. Verify Regularly

Schedule periodic verification to catch stale citations early:

```bash
# Weekly cron job
0 9 * * 1 cd /repo && python -m memory_enhancement verify-all
```

### 3. Prioritize by Confidence

Focus maintenance on low-confidence memories first:

```bash
# Generate health report
python -m memory_enhancement health

# Review critical memories (confidence < 0.5)
# Update or mark obsolete
```

### 4. Update After Refactoring

Always verify after major code changes:

```bash
# After merge
python -m memory_enhancement verify-all

# Review and fix stale citations
python -m memory_enhancement list-citations <memory-id>
```

### 5. Use Confidence in Decisions

Check confidence before relying on memories:

```python
# Pseudo-code
memory = load_memory("best-practices")
if memory.confidence < 0.7:
    warn("Memory may be outdated, verify manually")
```

### 6. Don't Over-Optimize

Confidence is a guideline, not an absolute truth:

- **0.8 is often good enough** - Don't chase 1.0 at all costs
- **Some staleness is acceptable** - Code moves, memories adapt
- **Focus on high-value memories** - Not every memory needs 100% confidence

### 7. Balance Citation Quantity

More citations ≠ better:

**Good:**

- 2-3 citations to key code locations
- Citations to stable, core functionality
- File-level citations for broad concepts

**Avoid:**

- 20+ citations to every line of code
- Citations to volatile test code
- Redundant citations to same area

**Example:**

```yaml
# Good - focused citations
citations:
  - path: src/api/auth.py
    line: 42
    snippet: "validate_token"
  - path: src/middleware/auth.ts
    line: 15
    snippet: "authenticate"

# Avoid - over-cited
citations:
  - path: src/api/auth.py
    line: 42
  - path: src/api/auth.py
    line: 43
  - path: src/api/auth.py
    line: 44
  # ... 15 more lines from same file
```

### 8. Document Intentional Low Confidence

Some memories should have low confidence:

```markdown
<!-- Memory: deprecated-pattern-001 -->
---
subject: Deprecated Authentication Pattern
confidence: 0.2
last_verified: 2026-01-24
citations:
  - path: old/auth_v1.py  # Intentionally stale
    valid: false
    mismatch_reason: "File removed in v2 migration"
---

**Note**: This pattern is deprecated. Low confidence is expected.
See: modern-auth-pattern-001 for current approach.
```

## Summary

**Key Takeaways:**

1. Confidence = valid_citations / total_citations
2. 0.9-1.0 = high trust, 0.0-0.5 = needs attention
3. Update after refactoring, deletions, or major changes
4. Use health reports to prioritize maintenance
5. Balance citation quantity with quality
6. Historical tracking (planned) will enable trend analysis
