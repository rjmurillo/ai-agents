# Gemini Code Assist: Path Exclusions

**Field**: `ignore_patterns` in `.gemini/config.yaml`

## Glob Pattern Syntax

Uses [VS Code glob patterns](https://code.visualstudio.com/docs/editor/glob-patterns):

| Pattern | Matches |
|---------|---------|
| `**/*.{ext}` | All files with extension anywhere |
| `**/folder/**` | Entire directory tree |
| `folder/*` | Direct children only |
| `!pattern` | Negation (include exception) |

## Recommended Exclusions

```yaml
ignore_patterns:
  - ".agents/**"           # Agent artifacts
  - ".serena/memories/**"  # Memory files
  - "**/*.generated.*"     # Generated code
  - "**/bin/**"            # Build outputs
  - "**/obj/**"            # Build outputs
  - "**/vendor/**"         # Third-party code
  - "**/node_modules/**"   # NPM dependencies
  - "**/*.min.js"          # Minified files
```

## Do Exclude

- Generated files (`**/*.generated.*`)
- Build outputs (`**/bin/**`, `**/obj/**`)
- Agent artifacts (`.agents/**`)
- Memory stores (`.serena/memories/**`)
- Third-party code (`**/vendor/**`)
- Minified files (`**/*.min.js`)

## Don't Exclude

- Core source code
- Test files (unless intentionally)
- Configuration files that should be reviewed
- Documentation
