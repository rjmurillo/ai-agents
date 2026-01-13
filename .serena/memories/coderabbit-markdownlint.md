## Integration

Disable CodeRabbit's markdownlint when project has `.markdownlint-cli2.yaml`:

```yaml
tools:
  markdownlint:
    enabled: false  # Already enforced by .markdownlint-cli2.yaml
```

## Auto-Suppressed Rules

MD004, MD012, MD013, MD025, MD026, MD032, MD033

## Related

- See `skills-linting` for markdownlint patterns (deferred to project config).
- [coderabbit-config-strategy](coderabbit-config-strategy.md)
- [coderabbit-documentation-false-positives](coderabbit-documentation-false-positives.md)
- [coderabbit-mcp-false-positives](coderabbit-mcp-false-positives.md)
- [coderabbit-path-instructions](coderabbit-path-instructions.md)
- [coderabbit-security-false-positives](coderabbit-security-false-positives.md)
