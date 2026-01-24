# Memory Citation Guide

## Overview

Citations in Serena memories provide traceability between knowledge and codebase locations. This enables automated staleness detection, confidence scoring, and verification of memory accuracy.

### Benefits

- **Staleness Detection**: Automatically detect when code referenced by memories changes or moves
- **Confidence Scoring**: Quantify memory reliability based on citation validity
- **Traceability**: Understand which code a memory references without manual search
- **CI Integration**: Block or warn on PRs that invalidate memory citations

### When to Add Citations

Add citations when memories reference:

- **Code patterns**: Implementation patterns, design decisions
- **Configuration**: Config files, environment variables, build settings
- **API definitions**: Endpoints, request/response formats, contracts
- **Architecture**: Component boundaries, data flows, system diagrams
- **Dependencies**: External libraries, frameworks, tool configurations

**Do not** add citations for:

- **General knowledge**: Language features, industry practices
- **Temporary notes**: Session logs, investigation notes (unless they reference specific code)
- **Future planning**: Roadmaps, ideas that don't yet exist in code

## Citation Schema

Citations are stored in YAML frontmatter at the top of memory markdown files.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | Relative file path from repository root (e.g., `scripts/Deploy.ps1`) |
| `verified` | datetime | ISO 8601 timestamp of last verification (e.g., `2026-01-24T12:00:00Z`) |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `line` | integer | Line number (1-indexed) for precise location |
| `snippet` | string | Code snippet for fuzzy matching when lines shift |

### Example

```yaml
---
id: security-002-input-validation
subject: Input Validation Pattern
citations:
  - path: scripts/Validate-Input.ps1
    line: 42
    snippet: "if ($Input -notmatch '^[a-zA-Z0-9]+$')"
    verified: 2026-01-24T10:30:00Z
  - path: scripts/api/Invoke-APICall.ps1
    line: 15
    verified: 2026-01-24T10:30:00Z
  - path: .github/workflows/security-scan.yml
    verified: 2026-01-24T10:30:00Z
tags:
  - security
  - validation
confidence: 1.0
---

# Input Validation Pattern

This memory documents the standard input validation pattern used across the codebase...
```

## Adding Citations

### Manual Method

1. Open the memory file in `.serena/memories/`
2. Add or update the `citations` array in the YAML frontmatter
3. Include required fields: `path` and `verified`
4. Optionally add `line` and `snippet` for precision
5. Save and verify: `python -m scripts.memory_enhancement verify <memory-id>`

### CLI Method (Future Phase 4)

```bash
# Add citation to existing memory
python -m scripts.memory_enhancement add-citation \
  --memory security-002-input-validation \
  --path scripts/Validate-Input.ps1 \
  --line 42 \
  --snippet "if ($Input -notmatch"

# Bulk add citations from git blame
python -m scripts.memory_enhancement auto-cite --memory <memory-id>
```

### Best Practices

1. **Use line numbers and snippets for precision**
   - Line numbers alone can become stale when code is refactored
   - Snippets enable fuzzy matching: if line 42 moves to line 45 but the snippet still matches, the citation remains valid

2. **Verify after adding**
   ```bash
   python -m scripts.memory_enhancement verify <memory-id>
   ```

3. **Keep citations focused**
   - Cite specific functions/classes, not entire files unless the whole file is relevant
   - Avoid over-citation: 3-5 citations per memory is typical

4. **Update verified timestamp**
   - Set `verified` to the current timestamp when adding or manually verifying a citation
   - CI will update this automatically during validation

## Verification Workflow

### Local Verification

**Single memory:**
```bash
python -m scripts.memory_enhancement verify security-002-input-validation
```

**Output example:**
```
✅ VALID - security-002-input-validation
Confidence: 100.0%
Citations: 3/3 valid
```

**All memories with citations:**
```bash
python -m scripts.memory_enhancement verify-all
```

**Output example:**
```
Verified 127 memories: 120 valid, 7 stale

Stale memories:

❌ STALE - pr-review-003
Confidence: 33.3%
Citations: 1/3 valid

Stale citations:
  - scripts/pr/Review-PR.ps1:102
    Reason: Line 102 exceeds file length (98 lines)
  - scripts/pr/Post-Comment.ps1:
    Reason: File not found: scripts/pr/Post-Comment.ps1
```

### Batch Health Check

```bash
python -m scripts.memory_enhancement health --format markdown
```

**Output:**
- Summary: Total memories, valid/stale counts, average confidence
- Stale memories: Detailed reasons for each stale citation
- Low confidence (<0.5): Memories needing review
- Orphaned memories (optional): Memories with no links

**JSON output** (for scripts/CI):
```bash
python -m scripts.memory_enhancement health --format json
```

### CI Integration

The `memory-validation.yml` workflow runs automatically on PRs that touch:
- `.serena/memories/**`
- `scripts/memory_enhancement/**`
- Python files in `scripts/**/*.py`

**Workflow behavior:**
1. Verifies all memories with citations
2. Generates health report
3. Posts PR comment with results
4. **Currently non-blocking** (warning mode)
5. Exit with error if stale citations found (can be enabled for blocking mode)

**Sample PR comment:**
```
## ⚠️ Warning: Memory Validation

### Summary
- **Total memories**: 933
- **Memories with citations**: 127
- **Valid memories**: 120 ✅
- **Stale memories**: 7 ❌
- **Average confidence**: 94.5%

### ❌ Stale Memories
...
```

## Interpreting Results

### Confidence Scores

| Score | Interpretation | Action |
|-------|----------------|--------|
| 1.0 (100%) | All citations valid | No action needed |
| 0.7-0.99 (70-99%) | Most citations valid | Review and update stale citations |
| 0.5-0.69 (50-69%) | Half of citations stale | Update or deprecate memory |
| <0.5 (<50%) | Majority of citations stale | Consider removing or rewriting memory |

**Calculation:** `confidence = valid_citations / total_citations`

For memories without citations, confidence defaults to `1.0` (assumes manual verification).

### Stale Citation Reasons

| Reason | Meaning | Remediation |
|--------|---------|-------------|
| `File not found: path/to/file` | File deleted or moved | Update path or remove citation |
| `Line X exceeds file length (Y lines)` | File shortened, line no longer exists | Update line number or remove citation |
| `Snippet not found in line X` | Line content changed | Update snippet or line number |
| `Error reading file: <error>` | Permissions or encoding issue | Fix file permissions or encoding |

## Examples

### Example 1: Code Pattern with Precise Citations

```yaml
---
id: implementation-002-test-driven
subject: Test-Driven Implementation Pattern
citations:
  - path: tests/Test-ValidationLogic.Tests.ps1
    line: 23
    snippet: "It 'validates input format' {"
    verified: 2026-01-24T11:00:00Z
  - path: scripts/Validate-Input.ps1
    line: 1
    snippet: "function Validate-Input {"
    verified: 2026-01-24T11:00:00Z
tags:
  - testing
  - implementation
confidence: 1.0
---

# Test-Driven Implementation Pattern

When implementing new validation logic, we follow TDD by writing tests first...
```

### Example 2: Configuration Reference

```yaml
---
id: ci-infrastructure-002-explicit-retry
subject: Explicit Retry Timing Configuration
citations:
  - path: .github/workflows/pytest.yml
    line: 87
    snippet: "timeout-minutes: 10"
    verified: 2026-01-24T11:15:00Z
  - path: .github/workflows/memory-validation.yml
    line: 53
    snippet: "timeout-minutes: 10"
    verified: 2026-01-24T11:15:00Z
tags:
  - ci-infrastructure
  - performance
confidence: 1.0
---

# Explicit Retry Timing Configuration

CI workflows should specify explicit timeouts to prevent infinite hangs...
```

### Example 3: Before/After Adding Citations

**Before (no citations):**
```yaml
---
id: security-003-secure-error-handling
subject: Secure Error Handling Pattern
tags:
  - security
  - error-handling
---

# Secure Error Handling Pattern

Error messages should not leak sensitive information...
```

**After (with citations):**
```yaml
---
id: security-003-secure-error-handling
subject: Secure Error Handling Pattern
citations:
  - path: scripts/error/Handle-Error.ps1
    line: 15
    snippet: 'Write-Host "An error occurred" -ForegroundColor Red'
    verified: 2026-01-24T12:00:00Z
  - path: tests/Test-ErrorHandling.Tests.ps1
    line: 42
    snippet: "It 'does not leak stack traces' {"
    verified: 2026-01-24T12:00:00Z
tags:
  - security
  - error-handling
confidence: 1.0
---

# Secure Error Handling Pattern

Error messages should not leak sensitive information...
```

## Link Types

Citations are references to code. For relationships between memories, use **links**:

```yaml
links:
  - link_type: RELATED
    target_id: security-001-input-validation
  - link_type: IMPLEMENTS
    target_id: adr-042-python-first-enforcement
  - link_type: SUPERSEDES
    target_id: security-003-old-error-handling
```

**Link types:**
- `RELATED`: General relationship
- `SUPERSEDES`: This memory replaces an older one
- `BLOCKS`: This memory blocks another (dependency)
- `IMPLEMENTS`: This memory implements an ADR/spec
- `EXTENDS`: This memory extends another with more detail

## Troubleshooting

### Problem: Verification fails with "Module not found"

**Solution:** Install dependencies:
```bash
# With UV
uv pip install --system -e ".[dev]"

# With pip
pip install -e ".[dev]"
```

### Problem: All citations show as stale after refactoring

**Solution:** Use `snippet` for fuzzy matching. If line 42 moves to line 50 but the snippet still matches, the citation remains valid. Update line numbers after major refactors.

### Problem: Health report shows 0 memories with citations

**Solution:** This is expected if no memories have citations yet. Start by adding citations to high-importance memories (e.g., security patterns, core architecture decisions).

### Problem: CI workflow doesn't trigger

**Solution:** Ensure your PR touches one of the trigger paths:
- `.serena/memories/**`
- `scripts/memory_enhancement/**`
- `scripts/**/*.py`
- `pyproject.toml`
- `uv.lock`

## References

- [PRD: Memory Enhancement Layer](../specs/PRD-memory-enhancement-layer-for-serena-forgetful.md)
- [ADR-038: Reflexion Memory Schema](../architecture/ADR-038-reflexion-memory-schema.md)
- [Memory Enhancement README](../../scripts/memory_enhancement/README.md)
- [GitHub Workflow: memory-validation.yml](../../.github/workflows/memory-validation.yml)
