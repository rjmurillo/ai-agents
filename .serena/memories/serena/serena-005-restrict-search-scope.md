# Skill: Always Restrict Search Scope with relative_path

**Skill ID**: skill-serena-005-restrict-search-scope
**Category**: Token Efficiency
**Impact**: High (70% scope reduction)
**Status**: Recommended

## Trigger Condition

When you know the general location of what you're searching for.

## Action Pattern

Always pass `relative_path` parameter to restrict search:

1. `search_for_pattern(pattern, relative_path="src/")`
2. `find_symbol(name, relative_path="src/config/")`
3. `get_symbols_overview(relative_path="src/models/")`

## Cost Benefit

Reduces search scope by 70-90%, decreasing token usage and improving response time.

## Evidence

From SERENA-BEST-PRACTICES.md lines 341-348:
- Unrestricted search scans entire codebase
- Scoped search targets specific directory
- Dramatic reduction in results and tokens

## Example

```text
# BAD: Search entire codebase (slow, many results)
search_for_pattern("TODO")

# GOOD: Search specific directory (fast, focused)
search_for_pattern("TODO", relative_path="src/")

# GOOD: Find symbol in known location
find_symbol("Config", relative_path="src/config/")
```

## Atomicity Score

97% - Single concept: use relative_path to restrict scope

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-004-find-symbol-patterns
- skill-serena-007-limit-tool-output
