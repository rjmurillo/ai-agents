# Size Validation for Memory Files

## Quick Start

```bash
# Validate single file
python3 test_memory_size.py .serena/memories/memory-index.md

# Validate all memories in directory
python3 test_memory_size.py .serena/memories --pattern "*.md"

# Recursive with fail-fast (exit on first failure)
python3 test_memory_size.py .serena/memories -r --pattern "*.md" --fail-fast

# Custom thresholds
python3 test_memory_size.py .serena/memories --max-chars 5000 --max-skills 10
```

## Thresholds

Default values from `memory-size-001-decomposition-thresholds`:

| Threshold | Default | Purpose |
|-----------|---------|---------|
| Max Characters | 10,000 | ~2,500 tokens, atomic memory size |
| Max Skills | 15 | Maximum ## headings per file |
| Max Categories | 5 | Maximum distinct concept groups |

## Exit Codes

| Code | Meaning | Use Case |
|------|---------|----------|
| 0 | All files valid | Pre-commit hook passes |
| 1 | Validation failures | Pre-commit hook blocks commit |

## Pre-Commit Integration

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Validate memory sizes before commit

echo "Validating memory sizes..."
python3 .claude/skills/memory/scripts/test_memory_size.py .serena/memories \
    --pattern "*.md" \
    --fail-fast

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Memory size validation failed"
    echo "See recommendations above for decomposition guidance"
    echo "Reference: .serena/memories/memory-size-001-decomposition-thresholds.md"
    exit 1
fi

echo "✅ Memory sizes within thresholds"
```

## Output Format

### Passing File

```text
✅ PASS: .serena/memories/memory-token-efficiency.md
  Characters: 3,875
  Skills: 15
  Categories: 3
```

### Failing File

```text
❌ FAIL: .serena/memories/skills-github-cli.md
  Characters: 38,000
  Skills: 42
  Categories: 7
  Violations:
    - Character count (38,000) exceeds maximum (10,000)
    - Skill count (42) exceeds maximum (15)
    - Category count (7) exceeds maximum (5)
  Recommendation: Decompose into 4 focused files. Target <10,000 chars per file. See memory-size-001-decomposition-thresholds.md
```

### Directory Summary

```text
Summary: 5/6 files passed validation

❌ 1 file(s) exceeded size thresholds
Run decomposition to fix (see memory-size-001-decomposition-thresholds.md)
```

## Validation Logic

### Character Count

Counts total UTF-8 characters in file. Threshold enforces atomic memory size (~2,500 tokens = 10,000 chars).

### Skill Count

Counts level-2 headings (`## Skill Name`). Each skill should be independently useful.

### Category Count

Heuristic detection:

1. Primary: Count H1 headings (excluding "TOC", "Overview", etc.)
2. Fallback: Extract unique prefixes from H2 headings (e.g., "Git:", "GitHub:")
3. Minimum: At least 1 category per file

## Common Violations and Fixes

| Violation | Root Cause | Fix |
|-----------|-----------|-----|
| >10,000 chars | Consolidated index file | Split by domain (pr-review-index → pr-review-operations, pr-review-patterns) |
| >15 skills | Topic too broad | Group related skills into category-specific files |
| >5 categories | Multiple domains | Separate into domain-specific memories |

## Context Engineering Principle

Size enforcement prevents token waste through progressive disclosure:

> "Memory files should be atomic (one retrievable concept) to avoid loading irrelevant content."

Token waste before decomposition:

- Large file: 9,500 tokens loaded
- Relevant content: 1,200 tokens
- **Waste: 8,300 tokens (87%)**

Token efficiency after decomposition:

- Targeted file: 1,200 tokens loaded
- Relevant content: 1,200 tokens
- **Waste: 0 tokens (0%)**

See: [Context Engineering Analysis](/.agents/analysis/context-engineering.md)

## Integration with Token Counter

Combine validation with token counting:

```bash
# Check size AND token cost
python3 test_memory_size.py .serena/memories/memory-index.md && \
python3 count_memory_tokens.py .serena/memories/memory-index.md
```

Output:

```text
✅ PASS: .serena/memories/memory-index.md
  Characters: 9,803
  Skills: 3
  Categories: 1

.serena/memories/memory-index.md: 2,450 tokens
```

## Troubleshooting

### False Positive: High Skill Count

If file has many small, related skills (e.g., CLI commands):

```bash
# Increase threshold temporarily
python3 test_memory_size.py file.md --max-skills 20
```

**Better fix**: Group related commands into sections with fewer top-level skills.

### False Positive: Category Detection

Manual override using H1 headings:

```markdown
# Category 1: Authentication

## Skill 1
## Skill 2

# Category 2: Authorization

## Skill 3
## Skill 4
```

Validator counts 2 categories (H1 headings).

## Related

- [Token Counter README](README-count-tokens.md)
- [Memory Size Thresholds](/.serena/memories/memory-size-001-decomposition-thresholds.md)
- [Context Engineering Analysis](/.agents/analysis/context-engineering.md)
