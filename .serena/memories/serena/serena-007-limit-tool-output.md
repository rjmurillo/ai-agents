# Skill: Limit Tool Output with max_answer_chars

**Skill ID**: skill-serena-007-limit-tool-output
**Category**: Token Efficiency
**Impact**: Medium (30-50% reduction in large codebases)
**Status**: Recommended

## Trigger Condition

When working with large codebases where tool output might be excessive.

## Action Pattern

Pass `max_answer_chars` parameter to limit response size:

```text
get_symbols_overview("src/", max_answer_chars=50000)
find_symbol("Config", max_answer_chars=30000)
search_for_pattern("TODO", max_answer_chars=20000)
```

## Cost Benefit

Reduces token usage by 30-50% in large codebases by truncating results at safe limit.

## Evidence

From SERENA-BEST-PRACTICES.md lines 360-368:
- Large codebases can return excessive results
- max_answer_chars parameter truncates output
- Prevents context overflow while preserving key information

## Example

```text
# Without limit: might return 100K chars (excessive)
get_symbols_overview("src/")

# With limit: returns max 50K chars (manageable)
get_symbols_overview("src/", max_answer_chars=50000)

# Adaptive limits based on tool
find_symbol("Config", max_answer_chars=30000)  # Focused query
search_for_pattern("TODO", max_answer_chars=20000)  # Potentially broad
```

## Atomicity Score

98% - Single concept: limit output size with max_answer_chars

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-005-restrict-search-scope
- skill-serena-008-configure-global-limits
