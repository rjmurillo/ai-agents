## Problem

66% noise ratio (33% Trivial + 33% Minor). Author spent 67% of review time dismissing noise.

## Solution: Tiered Enforcement

| Tier | Tool | Focus |
|------|------|-------|
| Primary | Automated tooling | `.markdownlint-cli2.yaml`, `dotnet format`, pre-commit hooks |
| Secondary | CodeRabbit (`chill`) | Logic errors, security, architecture |
| Critical | Security agent | Mandatory for infrastructure changes |

## Key Settings

| Control | Effect |
|---------|--------|
| `profile: chill` | Reduces nitpicky feedback |
| `path_instructions` with IGNORE | Most effective noise reduction |
| `markdownlint: enabled: false` | Prevents duplicate linting |
| `path_filters` | Exclude `.agents/**`, `.serena/**`, generated files |

**No severity threshold available** - use path_instructions instead.

## Success Metrics

| Metric | Before | Target |
|--------|--------|--------|
| Trivial + Minor | 66% | ~15% |
| False positives/PR | 4-5 | 0-1 |
| Signal-to-noise | 34% | >80% |

## Related

- [coderabbit-documentation-false-positives](coderabbit-documentation-false-positives.md)
- [coderabbit-markdownlint](coderabbit-markdownlint.md)
- [coderabbit-mcp-false-positives](coderabbit-mcp-false-positives.md)
- [coderabbit-path-instructions](coderabbit-path-instructions.md)
- [coderabbit-security-false-positives](coderabbit-security-false-positives.md)
