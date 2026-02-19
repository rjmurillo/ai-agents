# Citation Schema

Formal specification of the memory enhancement citation system. This system adds structured code references to Serena memory files. It enables automated staleness detection and confidence scoring at retrieval time.

## YAML Frontmatter Schema

Memory files use YAML frontmatter to store metadata, citations, and links. The markdown body follows after the closing `---`.

### Full Schema

```yaml
---
id: string              # Unique identifier. Defaults to filename stem if omitted.
subject: string         # Brief description of the memory.
citations:              # Array of code references (optional, defaults to []).
  - path: string        # Relative path from repo root (required).
    line: integer       # Line number, 1-based (optional).
    snippet: string     # Expected text on that line (optional).
    verified: datetime  # ISO-8601 timestamp of last verification (optional).
links:                  # Array of typed relationships to other memories (optional).
  - link_type: target_id  # key = LinkType enum value, value = target memory ID.
tags: [string]          # Classification tags (optional, defaults to []).
confidence: float       # 0.0 to 1.0 (optional, defaults to 0.5).
last_verified: datetime # ISO-8601 timestamp (optional).
---
Markdown content body
```

### Field Details

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | No | Filename stem | Unique memory identifier |
| `subject` | string | No | `""` | Brief description |
| `citations` | list | No | `[]` | Code location references |
| `citations[].path` | string | Yes (per item) | - | Relative file path from repo root |
| `citations[].line` | integer | No | `null` | 1-based line number |
| `citations[].snippet` | string | No | `null` | Expected text on the specified line |
| `citations[].verified` | datetime | No | `null` | ISO-8601 timestamp of last verification |
| `links` | list | No | `[]` | Relationships to other memories |
| `tags` | list[string] | No | `[]` | Classification tags |
| `confidence` | float | No | `0.5` | Reliability score from 0.0 to 1.0 |
| `last_verified` | datetime | No | `null` | ISO-8601 timestamp of last memory-level verification |

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
  - path: .github/workflows/security-scan.yml
    verified: 2026-01-24T10:30:00Z
links:
  - implements: adr-042-python-first-enforcement
tags:
  - security
  - validation
confidence: 1.0
---

# Input Validation Pattern

This memory documents the standard input validation pattern...
```

## Citation Verification Rules

The `verify_citation` function in `citations.py` applies checks in this order. It stops at the first failure.

### Verification Algorithm

```text
1. Resolve citation path against repo root.
2. Path traversal check: resolved path MUST be within repo root.
   - Fail: "Path traversal blocked: {path}"
3. File existence check.
   - Fail: "File not found: {path}"
4. If no line number, mark VALID. Stop.
5. Read file contents (UTF-8).
   - Fail on read error: "Cannot read file: {error}"
6. Line number range check: must be >= 1.
   - Fail: "Invalid line number: {line} (must be >= 1)"
7. Line number range check: must be <= file length.
   - Fail: "Line {line} exceeds file length ({length})"
8. If snippet provided, substring match on the specified line.
   - Fail: "Snippet mismatch at line {line}. Expected '{snippet}', got '{actual}'"
9. Mark VALID.
```

### Confidence Calculation

After verifying all citations in a memory:

```text
confidence = valid_citations / total_citations
```

If a memory has zero citations, its existing `confidence` value is preserved (default: 0.5).

### Failure Reasons Reference

| Reason | Cause | Fix |
|--------|-------|-----|
| Path traversal blocked | Path resolves outside repo root | Use relative paths, no `../` escapes |
| File not found | Referenced file deleted or moved | Update `path` or remove citation |
| Cannot read file | Permissions or encoding error | Fix file access |
| Invalid line number | Line < 1 | Use 1-based line numbers |
| Line exceeds file length | File shortened | Update or remove `line` |
| Snippet mismatch | Line content changed | Update `snippet` and/or `line` |

## Link Types

Links express typed relationships between memories. Each link entry is a single key-value pair where the key is the link type and the value is the target memory ID.

### Syntax

```yaml
links:
  - related: other-memory-id
  - supersedes: old-memory-id
```

### Enum Values

| Link Type | Semantics |
|-----------|-----------|
| `related` | General association between memories. |
| `supersedes` | This memory replaces the target. The target is obsolete. |
| `blocks` | This memory must be resolved before the target can proceed. |
| `implements` | This memory implements the target specification (e.g., an ADR). |
| `extends` | This memory adds detail to the target. |

Unknown link types are logged as warnings and skipped during parsing.

## CLI Reference

### Verify a Single Memory

```bash
python -m memory_enhancement verify <memory-id-or-path> [--json] [--repo-root PATH] [--dir PATH]
```

The `<memory-id-or-path>` argument resolves in this order:

1. Literal file path (must be within repo root).
2. `{memory-id}.md` in the memories directory.
3. Bare filename in the memories directory.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | off | Output JSON instead of human-readable text |
| `--repo-root` | `.` | Repository root directory |
| `--dir` | `.serena/memories` | Memories directory |

### Verify All Memories

```bash
python -m memory_enhancement verify-all [--json] [--repo-root PATH] [--dir PATH]
```

Scans all `.md` files in the memories directory. Only processes files that contain citations. Options are the same as `verify`.

### Output Formats

**Human-readable:**

```text
[PASS] security-002-input-validation: VALID
  Citations: 2/2 valid
  Confidence: 1.00

[FAIL] pr-review-003: STALE
  Citations: 1/3 valid
  Confidence: 0.33
  [STALE] scripts/pr/Review-PR.ps1:102
    Reason: Line 102 exceeds file length (98 lines)
```

**JSON** (`--json`):

```json
{
  "memory_id": "pr-review-003",
  "valid": false,
  "total_citations": 3,
  "valid_count": 1,
  "confidence": 0.33,
  "stale_citations": [
    {
      "path": "scripts/pr/Review-PR.ps1",
      "line": 102,
      "snippet": null,
      "mismatch_reason": "Line 102 exceeds file length (98 lines)"
    }
  ]
}
```

## Integration

### CI Workflow

The `citation-verify.yml` workflow runs on pull requests targeting `main`. It uses `dorny/paths-filter` to detect changes in:

- `.serena/memories/**`
- `.claude/skills/memory-enhancement/**`

When changes are detected, the workflow:

1. Sets up Python 3.12 with dependencies.
2. Runs `verify-all` against `.serena/memories/`.
3. Exits non-zero if stale citations are found.

### Pre-commit Hook

```bash
python -m memory_enhancement verify-all --repo-root "$(git rev-parse --show-toplevel)"
```

Add to `.githooks/pre-commit` or a pre-commit framework configuration. The command exits non-zero when stale citations exist.

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All citations valid (or no citations found) |
| `1` | One or more stale citations detected |
| `2` | Error (file not found, parse failure, invalid arguments) |
