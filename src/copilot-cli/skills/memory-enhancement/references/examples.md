# Memory Enhancement Examples

Practical examples of using the memory enhancement CLI and skill.

## Table of Contents

1. [Adding Citations](#adding-citations)
2. [Verifying Citations](#verifying-citations)
3. [Updating Confidence](#updating-confidence)
4. [Health Monitoring](#health-monitoring)
5. [Integration Workflows](#integration-workflows)

## Adding Citations

### Example 1: Add Citation to Existing Memory

Add a citation linking a memory to specific code:

```bash
# Add file-level citation
python -m memory_enhancement add-citation git-hooks-pre-commit \
  --file .git/hooks/pre-commit

# Add line-specific citation with snippet
python -m memory_enhancement add-citation security-002-input-validation-first \
  --file src/api/validate.py \
  --line 42 \
  --snippet "def validate_input"
```

**Output:**

```text
✅ Citation added to git-hooks-pre-commit
   File: .git/hooks/pre-commit:
```

### Example 2: Preview Before Adding (Dry Run)

Test citation addition without modifying files:

```bash
python -m memory_enhancement add-citation test-memory \
  --file src/test.py \
  --line 10 \
  --dry-run
```

**Output:**

```text
[DRY RUN] Would add citation to .serena/memories/test-memory.md
  File: src/test.py
  Line: 10
  Snippet: N/A
```

### Example 3: Handle Invalid Citations

What happens when citing non-existent code:

```bash
python -m memory_enhancement add-citation memory-001 \
  --file src/missing.py \
  --line 999
```

**Output (Exit Code 2):**

```text
Error: Invalid citation: File not found: src/missing.py
```

## Verifying Citations

### Example 1: Verify Single Memory

Check if a memory's citations are still valid:

```bash
python -m memory_enhancement verify security-002-input-validation-first
```

**Output:**

```text
✅ VALID - security-002-input-validation-first
Confidence: 100.0%
Citations: 2/2 valid
```

### Example 2: Verify with Stale Citations

Memory with outdated references:

```bash
python -m memory_enhancement verify pr-review-001-reviewer-enumeration
```

**Output (Exit Code 1):**

```text
❌ STALE - pr-review-001-reviewer-enumeration
Confidence: 50.0%
Citations: 1/2 valid

Stale citations:
  - src/reviewers.ts:42
    Reason: Line 42 exceeds file length (38 lines)
```

### Example 3: Batch Verification

Verify all memories in the directory:

```bash
python -m memory_enhancement verify-all
```

**Output:**

```text
Verified 25 memories: 20 valid, 5 stale

Stale memories:

❌ STALE - pr-review-001-reviewer-enumeration
Confidence: 50.0%
Citations: 1/2 valid

Stale citations:
  - src/reviewers.ts:42
    Reason: Line 42 exceeds file length (38 lines)

❌ STALE - implementation-002-test-driven-implementation
Confidence: 0.0%
Citations: 0/3 valid

Stale citations:
  - tests/unit/test_api.py:15
    Reason: File not found: tests/unit/test_api.py
  - src/api.py:100
    Reason: Snippet not found in line 100. Expected: 'validate_request', Found: 'def process_request()'
```

### Example 4: JSON Output for Automation

Get machine-readable verification results:

```bash
python -m memory_enhancement verify memory-001 --json
```

**Output:**

```json
{
  "memory_id": "memory-001",
  "valid": false,
  "confidence": 0.6667,
  "total_citations": 3,
  "valid_count": 2,
  "stale_citations": [
    {
      "path": "src/old.py",
      "line": 10,
      "snippet": "process",
      "mismatch_reason": "File not found: src/old.py"
    }
  ]
}
```

## Updating Confidence

### Example 1: Recalculate Confidence Score

After code changes, update confidence:

```bash
python -m memory_enhancement update-confidence security-002-input-validation-first
```

**Output:**

```text
✅ Confidence updated for security-002-input-validation-first
   Confidence: 100.0%
   Citations: 2/2 valid
```

### Example 2: Update After Refactoring

When confidence drops due to code changes:

```bash
python -m memory_enhancement update-confidence implementation-002-test-driven-implementation
```

**Output (Exit Code 1):**

```text
✅ Confidence updated for implementation-002-test-driven-implementation
   Confidence: 33.3%
   Citations: 1/3 valid

⚠️  2 stale citation(s) found
```

## Health Monitoring

### Example 1: Generate Health Report

Overview of memory citation health:

```bash
python -m memory_enhancement health
```

**Output:**

```markdown
# Memory Health Report

**Generated**: 2026-01-24T15:30:00
**Total Memories**: 450
**With Citations**: 85

## Summary

- **Valid**: 70 (82.4%)
- **Stale**: 15 (17.6%)

## Stale Memories (Ranked by Staleness)

### Critical (Confidence < 0.5)

1. **implementation-002-test-driven-implementation** (0.0%)
   - 0/3 citations valid
   - Last verified: 2026-01-20

2. **pr-review-001-reviewer-enumeration** (0.33%)
   - 1/3 citations valid
   - Last verified: 2026-01-22

### Warning (Confidence 0.5-0.7)

1. **security-004-security-event-logging** (0.67%)
   - 2/3 citations valid
   - Last verified: 2026-01-23

## Recommendations

- Review/update 2 critical memories (confidence < 0.5)
- Consider adding citations to 365 memories without citations
```

### Example 2: JSON Health Report for CI

Machine-readable health metrics:

```bash
python -m memory_enhancement health --format json
```

**Output:**

```json
{
  "generated_at": "2026-01-24T15:30:00",
  "total_memories": 450,
  "with_citations": 85,
  "valid_count": 70,
  "stale_count": 15,
  "stale_percentage": 17.6,
  "critical_memories": [
    {
      "id": "implementation-002-test-driven-implementation",
      "confidence": 0.0,
      "total_citations": 3,
      "valid_count": 0,
      "last_verified": "2026-01-20T10:15:00"
    }
  ]
}
```

### Example 3: Include Graph Analysis

Detect orphaned memories:

```bash
python -m memory_enhancement health --include-graph
```

Adds section:

```markdown
## Graph Connectivity

- **Connected**: 80 memories
- **Orphaned**: 5 memories (no incoming/outgoing links)

### Orphaned Memories

1. legacy-pattern-001
2. temp-debug-note
3. old-architecture-001
```

## Integration Workflows

### Workflow 1: Adding Citations During Reflection

When using `/reflect` skill:

1. User triggers reflection
2. Agent extracts learnings with code references
3. Agent detects pattern: "Bug in `src/api.py` line 42"
4. Agent auto-adds citation:

```bash
python -m memory_enhancement add-citation reflect-observations \
  --file src/api.py \
  --line 42 \
  --snippet "Bug"
```

5. Learning persisted with citation attached

### Workflow 2: Pre-Commit Validation

Verify citations before committing:

```bash
# In pre-commit hook
python -m memory_enhancement verify-all --json > /tmp/memory-results.json

if [ $? -ne 0 ]; then
  echo "⚠️  Stale memory citations detected. Run 'python -m memory_enhancement health' for details."
  echo "Consider updating memories before committing code changes."
  # Non-blocking (warning only)
fi
```

### Workflow 3: Weekly Health Check

Automated health monitoring:

```bash
# In CI cron job (runs weekly)
python -m memory_enhancement health --format markdown > memory-health.md
gh issue comment 123 --body-file memory-health.md
```

Creates comment on tracking issue with health metrics.

### Workflow 4: Post-Refactoring Cleanup

After major code refactoring:

```bash
# 1. Verify all citations
python -m memory_enhancement verify-all

# 2. Generate health report
python -m memory_enhancement health

# 3. For each stale memory (manual review):
python -m memory_enhancement list-citations <memory-id>

# 4. Update or remove stale citations
# - If code moved: update citation
# - If code deleted: mark memory obsolete or remove citation

# 5. Update confidence scores
python -m memory_enhancement update-confidence <memory-id>
```

## Troubleshooting

### Issue: "Memory not found"

**Symptom:**

```text
Error: Memory not found: my-memory
```

**Solution:** Use full filename or correct memory ID:

```bash
# Try with .md extension
python -m memory_enhancement verify my-memory.md

# Or use full path
python -m memory_enhancement verify .serena/memories/my-memory.md
```

### Issue: "Invalid citation" on Add

**Symptom:**

```text
Error: Invalid citation: File not found: src/foo.py
```

**Solution:** Verify file exists and path is repo-relative:

```bash
# Check file exists
ls -la src/foo.py

# Use repo-relative path (not absolute)
python -m memory_enhancement add-citation memory-001 \
  --file src/foo.py \
  --line 10
```

### Issue: Confidence Not Updating

**Symptom:** Confidence score remains unchanged after verification.

**Solution:** Explicitly run `update-confidence`:

```bash
# Verify detects stale citations but doesn't update file
python -m memory_enhancement verify memory-001

# Must explicitly update confidence
python -m memory_enhancement update-confidence memory-001
```

Alternatively, use `verify-all` which updates confidence automatically.
