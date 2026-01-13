## Effective path_instructions Pattern

```yaml
path_instructions:
  - path: "**/*.cs"
    instructions: |
      FOCUS ON: Security, logic errors, race conditions
      IGNORE: style (dotnet format), naming (analyzers), XML docs

  - path: ".github/workflows/**"
    instructions: |
      Profile: ASSERTIVE - security-critical infrastructure
      Flag: Unquoted variables, injection, missing error handling
```

## Path Filters (Noise Reduction)

```yaml
path_filters:
  - '!.agents/**'
  - '!.serena/**'
  - '!**/obj/**'
  - '!**/bin/**'
  - '!**/*.Designer.cs'
  - '!**/*.generated.cs'
```

**Impact**: ~60% noise reduction with optimized configuration.

## Related

- [coderabbit-config-strategy](coderabbit-config-strategy.md)
- [coderabbit-documentation-false-positives](coderabbit-documentation-false-positives.md)
- [coderabbit-markdownlint](coderabbit-markdownlint.md)
- [coderabbit-mcp-false-positives](coderabbit-mcp-false-positives.md)
- [coderabbit-security-false-positives](coderabbit-security-false-positives.md)
