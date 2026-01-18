# Skill: Use Symbolic Tools Before Full File Reads

**Skill ID**: skill-serena-001-symbolic-tools-first
**Category**: Token Efficiency
**Impact**: High (95% token reduction)
**Status**: Mandatory

## Trigger Condition

When you need to understand or locate code in a source file.

## Action Pattern

1. Start with `mcp__serena__get_symbols_overview(file_path)` to see structure
2. Use `mcp__serena__find_symbol(name_path, include_body=True)` for targeted reads
3. Only use `Read(file_path)` as last resort for non-code files

## Cost Benefit

| Approach | Token Usage | Savings |
|----------|-------------|---------|
| Read entire file | 2000 tokens | Baseline |
| get_symbols_overview | 100 tokens | 95% reduction |
| find_symbol with body | 200 tokens | 90% reduction |

## Evidence

From SERENA-BEST-PRACTICES.md lines 298-304:
- Full file read consumes 100% of file tokens
- Symbolic overview consumes ~5% of file tokens
- Targeted symbol read consumes ~10-20% of file tokens

## Example

```text
# BAD: Read full file (2000 tokens)
Read("src/large-file.ts")

# GOOD: Use symbolic tools (300 tokens total)
get_symbols_overview("src/large-file.ts")  # 100 tokens
find_symbol("ClassName", include_body=True)  # 200 tokens
```

## Atomicity Score

98% - Single concept: prefer symbolic tools over file reads

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-002-avoid-redundant-reads
- skill-serena-004-find-symbol-patterns
