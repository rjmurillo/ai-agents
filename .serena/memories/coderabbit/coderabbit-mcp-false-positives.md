## Skill-001: MCP Tool Path Case Sensitivity (95%)

MCP tool paths (`github/*`, `cloudmcp-manager/*`) are case-sensitive. Don't suggest capitalizing to "GitHub".

**Evidence**: PR #15

## Skill-002: Template Bracket Placeholders (93%)

`[List of...]` in agent templates are runtime placeholders, not incomplete docs.

**Evidence**: PR #15

## Skill-005: MCP Tool Duplicated Segments (92%)

`mcp__cloudmcp-manager__commicrosoftmicrosoft-learn...` - repeated segments follow MCP naming convention. Not duplication errors.

**Evidence**: PR #32

## Quick Dismissal

| Pattern | Action |
|---------|--------|
| MCP path capitalization | Dismiss |
| `[List of ...]` flagged | Dismiss |
| Repeated MCP segments | Dismiss |

## Related

- [coderabbit-config-strategy](coderabbit-config-strategy.md)
- [coderabbit-documentation-false-positives](coderabbit-documentation-false-positives.md)
- [coderabbit-markdownlint](coderabbit-markdownlint.md)
- [coderabbit-path-instructions](coderabbit-path-instructions.md)
- [coderabbit-security-false-positives](coderabbit-security-false-positives.md)
