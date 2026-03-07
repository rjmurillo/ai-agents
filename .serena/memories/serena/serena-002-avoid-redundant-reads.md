# Skill: Never Read What You Already Have

**Skill ID**: skill-serena-002-avoid-redundant-reads
**Category**: Token Efficiency
**Impact**: High (100% waste prevention)
**Status**: Mandatory

## Trigger Condition

When you have already read a file's content into context.

## Action Pattern

Once a file is in context via Read tool:
- DO NOT call get_symbols_overview on same file
- DO NOT call find_symbol on same file
- Context already contains the information

## Cost Benefit

Prevents 100% redundant token usage. If file is 2000 tokens and already read, symbolic analysis wastes another 100-200 tokens for duplicate information.

## Evidence

From SERENA-BEST-PRACTICES.md lines 306-313:
- Reading file then analyzing it with symbolic tools is redundant
- Correct flow: symbolic analysis first, then read only specific symbols

## Example

```text
# BAD: Redundant analysis
Read("config.py")  # File now in context
get_symbols_overview("config.py")  # Wasteful - you already have it

# GOOD: Symbolic first, read last
get_symbols_overview("config.py")  # Structure only
find_symbol("Config/database_url", include_body=True)  # Targeted read
```

## Atomicity Score

100% - Single concept: avoid redundant reads

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-001-symbolic-tools-first
