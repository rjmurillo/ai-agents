# Skill: Use find_symbol with Pattern Matching

**Skill ID**: skill-serena-004-find-symbol-patterns
**Category**: Token Efficiency
**Impact**: Medium (50% search efficiency)
**Status**: Recommended

## Trigger Condition

When searching for symbols by name or pattern.

## Action Pattern

Use `mcp__serena__find_symbol` with these strategies:

1. **Substring matching**: `find_symbol("get", substring_matching=True)` finds all "get*" methods
2. **Path-qualified**: `find_symbol("MyClass/myMethod")` finds specific method
3. **Relative path**: `find_symbol("Config", relative_path="src/config/")` restricts scope
4. **Overview mode**: `find_symbol("ClassName", include_body=False, depth=1)` shows structure only

## Cost Benefit

Reduces search scope and token usage by 50-80% compared to full codebase search.

## Evidence

From SERENA-BEST-PRACTICES.md lines 325-339:
- Pattern matching finds symbols without reading full files
- Relative path restriction reduces search scope
- Overview mode (include_body=False) minimizes tokens

## Example

```text
# Find all "get" methods (substring match)
find_symbol("get", substring_matching=True)

# Find specific method in class
find_symbol("MyClass/myMethod")

# Restrict to directory (faster, fewer results)
find_symbol("Config", relative_path="src/config/")

# Get class structure without bodies (minimal tokens)
find_symbol("ClassName", include_body=False, depth=1)
```

## Atomicity Score

92% - Single concept: use find_symbol with appropriate patterns and restrictions

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-001-symbolic-tools-first
- skill-serena-005-restrict-search-scope
