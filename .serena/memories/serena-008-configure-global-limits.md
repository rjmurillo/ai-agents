# Skill: Configure Global Token Limits

**Skill ID**: skill-serena-008-configure-global-limits
**Category**: Setup
**Impact**: High (project-wide 30% token reduction)
**Status**: Recommended

## Trigger Condition

When setting up Serena for a project or adjusting token efficiency globally.

## Action Pattern

Edit `~/.serena/serena_config.yml`:

```yaml
# Reduce from default 150000 to 50000-75000
default_max_tool_answer_chars: 50000

# Use accurate token estimator
token_count_estimator: ANTHROPIC_CLAUDE_SONNET_4
```

## Cost Benefit

Reduces project-wide token usage by 30% by limiting all tool outputs globally.

## Evidence

From SERENA-BEST-PRACTICES.md lines 209-227:
- Default max_tool_answer_chars is 150000
- Recommended value: 50000-75000
- Applies to all tools unless overridden per-call

## Example

```yaml
# ~/.serena/serena_config.yml
default_max_tool_answer_chars: 50000  # Lower than default 150000
token_count_estimator: ANTHROPIC_CLAUDE_SONNET_4  # Accurate tracking
```

## Atomicity Score

95% - Single concept: set global token limits in config

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-007-limit-tool-output
- skill-serena-009-use-claude-code-context
